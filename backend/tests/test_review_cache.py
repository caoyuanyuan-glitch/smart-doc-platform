import json
import asyncio
from types import SimpleNamespace

from app.api import review as review_api


def test_build_review_cache_key_changes_with_mode(monkeypatch):
    monkeypatch.setattr(review_api, "_review_cache_version", lambda: "v1")
    document = SimpleNamespace(
        id=1,
        filename="demo.docx",
        file_type="docx",
        file_size=128,
        content="same content",
    )

    rule_key = review_api._build_review_cache_key(document, "rule")
    hybrid_key = review_api._build_review_cache_key(document, "hybrid")

    assert rule_key != hybrid_key


def test_review_cache_version_tracks_review_basis_files():
    for path in review_api.REVIEW_BASIS_VERSION_FILES:
        assert path in review_api.REVIEW_CACHE_VERSION_FILES


def test_find_cached_completed_review_matches_cache_key(monkeypatch):
    expected_key = "cache-key-1"
    monkeypatch.setattr(review_api, "_build_review_cache_key", lambda document, mode: expected_key)

    matched_review = SimpleNamespace(
        id=12,
        status="completed",
        total_issues=3,
        summary=json.dumps({"cache_key": expected_key, "total": 3}),
    )
    unmatched_review = SimpleNamespace(
        id=11,
        status="completed",
        total_issues=5,
        summary=json.dumps({"cache_key": "other-key", "total": 5}),
    )
    monkeypatch.setattr(review_api, "get_reviews", lambda db, document_id, limit=20: [unmatched_review, matched_review])

    review, summary = review_api._find_cached_completed_review(None, SimpleNamespace(id=7), "rule")

    assert review.id == 12
    assert summary["total"] == 3


def test_find_cached_completed_review_skips_non_completed(monkeypatch):
    monkeypatch.setattr(review_api, "_build_review_cache_key", lambda document, mode: "cache-key-1")
    reviews = [
        SimpleNamespace(id=21, status="running", summary=json.dumps({"cache_key": "cache-key-1"})),
        SimpleNamespace(id=22, status="failed", summary=json.dumps({"cache_key": "cache-key-1"})),
    ]
    monkeypatch.setattr(review_api, "get_reviews", lambda db, document_id, limit=20: reviews)

    review, summary = review_api._find_cached_completed_review(None, SimpleNamespace(id=7), "rule")

    assert review is None
    assert summary is None


def test_list_reviews_batches_document_lookup(monkeypatch):
    reviews = [
        SimpleNamespace(id=3, document_id=11, status="running", summary="", total_issues=0),
        SimpleNamespace(id=2, document_id=12, status="completed", summary="{}", total_issues=4),
    ]
    documents = [
        SimpleNamespace(id=11, filename="a.docx", file_type="docx"),
        SimpleNamespace(id=12, filename="b.pdf", file_type="pdf"),
    ]
    calls = []

    monkeypatch.setattr(review_api, "get_reviews", lambda db: reviews)
    monkeypatch.setattr(review_api, "_reconcile_review_runtime_state", lambda db, review: review)
    monkeypatch.setattr(review_api, "get_progress", lambda review_id: {"status": "running", "progress": 35, "message": "处理中"})

    def fake_get_documents_by_ids(db, document_ids):
        calls.append(list(document_ids))
        return documents

    monkeypatch.setattr(review_api, "get_documents_by_ids", fake_get_documents_by_ids)

    result = asyncio.run(review_api.list_reviews(db=None))

    assert calls == [[11, 12]]
    assert result[0]["document_name"] == "a.docx"
    assert result[0]["progress"]["progress"] == 35
    assert result[1]["document_file_type"] == "pdf"


def test_normalize_review_status_accepts_supported_values():
    assert review_api._normalize_review_status(None) is None
    assert review_api._normalize_review_status("all") is None
    assert review_api._normalize_review_status("RUNNING") == "running"


def test_list_reviews_supports_filters(monkeypatch):
    reviews = [SimpleNamespace(id=8, document_id=21, status="running", summary="", total_issues=0)]
    documents = [SimpleNamespace(id=21, filename="demo.docx", file_type="docx")]
    captured = {}

    def fake_query_review_rows(db, document_id=None, status=None, latest_only=False, limit=100):
        captured.update({
            "document_id": document_id,
            "status": status,
            "latest_only": latest_only,
            "limit": limit,
        })
        return reviews

    monkeypatch.setattr(review_api, "_query_review_rows", fake_query_review_rows)
    monkeypatch.setattr(review_api, "get_documents_by_ids", lambda db, document_ids: documents)
    monkeypatch.setattr(review_api, "_reconcile_review_runtime_state", lambda db, review: review)
    monkeypatch.setattr(review_api, "get_progress", lambda review_id: {"status": "running", "progress": 42, "message": "处理中"})

    result = asyncio.run(
        review_api.list_reviews(document_id=21, status="running", latest_only=True, limit=25, db=None)
    )

    assert captured == {"document_id": 21, "status": "running", "latest_only": True, "limit": 25}
    assert result[0]["document_name"] == "demo.docx"
    assert result[0]["progress"]["progress"] == 42


def test_select_relevant_ai_review_basis_prefers_matching_sections():
    sections = [
        {"label": "通用风格", "text": "【通用风格】\n统一标点和语法。", "priority": 2},
        {"label": "版本记录", "text": "【版本记录】\nrevision history copyright year version history", "priority": 5},
        {"label": "术语", "text": "【术语】\n术语一致性与缩略语。", "priority": 3},
    ]

    selected = review_api._select_relevant_ai_review_basis(
        "Please check revision history and copyright year consistency.",
        sections,
        max_sections=2,
        char_budget=500,
    )

    assert "版本记录" in selected
    assert "revision history" in selected


def test_build_ai_review_basis_sections_include_english_and_common_error_specs():
    sections = review_api._build_ai_review_basis_sections(
        {
            "en_style": "Use present tense. Use active voice. Use sentence style headings.",
            "common_errors": "中文文档统一使用全角标点。单位统一使用 μL、mL、kg。",
        },
        "both",
    )

    labels = {section["label"] for section in sections}

    assert "英文技术文档写作风格指南" in labels
    assert "技术文档常见错误清单" in labels


def test_run_cached_ai_chunk_review_reuses_cached_result(monkeypatch):
    review_api._ai_review_chunk_cache.clear()
    calls = []

    monkeypatch.setattr(review_api, "_review_cache_version", lambda: "v-cache")
    monkeypatch.setattr(review_api, "_ai_provider_cache_fingerprint", lambda: "provider-a")

    def fake_call_with_timeout(func, timeout_seconds, *args, **kwargs):
        calls.append((timeout_seconds, args[0], args[2], args[4], args[5]))
        return {"issues": [{"rule": "AI", "original_text": "demo"}]}

    monkeypatch.setattr(review_api, "_call_with_timeout", fake_call_with_timeout)

    first, first_hit = review_api._run_cached_ai_chunk_review(88, "chunk-a", "en", "basis-a", 18)
    second, second_hit = review_api._run_cached_ai_chunk_review(88, "chunk-a", "en", "basis-a", 18)

    assert first_hit is False
    assert second_hit is True
    assert first == second
    assert len(calls) == 1
    assert calls[0] == (18, "chunk-a", "basis-a", 88, "review.audit_chunk")


def test_log_review_ai_usage_prints_summary(monkeypatch, capsys):
    monkeypatch.setattr(
        review_api.ai_client,
        "summarize_usage_events",
        lambda request_label=None, review_id=None, limit=200: {
            "calls": 2,
            "prompt_tokens": 120,
            "completion_tokens": 30,
            "total_tokens": 150,
            "providers": {"kimi": 2},
        },
    )

    review_api._log_review_ai_usage(66, "review.audit_chunk", "AI深度审核Token统计")

    output = capsys.readouterr().out
    assert "AI深度审核Token统计" in output
    assert "total_tokens=150" in output


def test_review_ai_chunk_limit_defaults_to_eight(monkeypatch):
    monkeypatch.delenv("REVIEW_AI_MAX_CHUNKS", raising=False)

    # P0-2: 默认上限已从 8 提升到 32，支持动态计算
    assert review_api._review_ai_chunk_limit() == 32


def test_review_ai_token_budget_defaults_to_zero(monkeypatch):
    monkeypatch.delenv("REVIEW_AI_TOKEN_BUDGET", raising=False)

    assert review_api._review_ai_token_budget() == 0


def test_run_ai_deep_review_stops_when_budget_reached(monkeypatch):
    chunks = [
        (1, 0, "chunk-1"),
        (2, 100, "chunk-2"),
        (3, 200, "chunk-3"),
    ]
    processed = []
    usage_state = {"tokens": 0}

    monkeypatch.setattr(review_api, "_iter_ai_audit_chunks", lambda content: chunks)
    monkeypatch.setattr(review_api, "_review_ai_chunk_limit", lambda content_length: 3)
    monkeypatch.setattr(review_api, "_review_ai_token_budget", lambda: 200)
    monkeypatch.setattr(review_api, "set_progress", lambda *args, **kwargs: None)
    monkeypatch.setattr(review_api, "_select_relevant_ai_review_basis", lambda chunk, sections: "basis")

    def fake_run_cached_ai_chunk_review(review_id, chunk, document_language, audit_basis, chunk_timeout, force_provider=None):
        processed.append(chunk)
        usage_state["tokens"] += 120
        return ([{"rule": "AI", "chapter": ""}], False)

    monkeypatch.setattr(review_api, "_run_cached_ai_chunk_review", fake_run_cached_ai_chunk_review)
    monkeypatch.setattr(
        review_api.ai_client,
        "summarize_usage_events",
        lambda request_label=None, review_id=None, limit=200: {
            "calls": len(processed),
            "prompt_tokens": max(usage_state["tokens"] - 20 * len(processed), 0),
            "completion_tokens": 20 * len(processed),
            "total_tokens": usage_state["tokens"],
            "providers": {"kimi": len(processed)} if processed else {},
        },
    )

    issues, chunk_meta = review_api._run_ai_deep_review(9, "demo content", "en", [{"text": "basis"}])

    assert processed == ["chunk-1", "chunk-2"]
    assert len(issues) == 2
    assert len(chunk_meta) == 2  # P0-3: 新增分块元数据返回


def test_chinese_human_baseline_rules_cover_common_spellcheck_sample_cases():
    content = (
        "试剂盒组份包括 Buffer。使用移液枪吸取 10ul 溶液，反应体系总体积为 20uL，在室温下静置 5 mins。"
        "将样本加入至离心管中，该试剂盒可用于用于 RNA 提取。"
        "否则的话，该步骤非常的重要。建议用户在使用前仔细阅读说明书。"
        "PCR 扩增条件：95℃ 预变性。设置转数为12000rpm，避免污然样本。"
        "该产品的有效期为 12 个月，请在有效期内使用，过期请勿使用。"
    )

    issues = review_api._run_chinese_human_baseline_rules(content)
    originals = {issue["original_text"] for issue in issues}
    rules = {issue["rule"] for issue in issues}

    assert {
        "组份",
        "10ul",
        "20uL",
        "5 mins",
        "加入至",
        "可用于用于",
        "否则的话",
        "非常的重要",
        "建议用户",
        "95℃",
        "转数",
        "12000rpm",
        "污然",
        "过期请勿使用",
    }.issubset(originals)
    assert {
        "CYY-CN-SPELL-001",
        "CYY-CN-UNIT-001",
        "CYY-CN-UNIT-002",
        "CYY-CN-UNIT-003",
        "CYY-CN-TERM-004",
        "CYY-CN-UNIT-004",
        "CYY-CN-SPELL-002",
        "CYY-CN-GRAMMAR-001",
        "CYY-CN-GRAMMAR-002",
        "CYY-CN-GRAMMAR-003",
        "CYY-CN-GRAMMAR-004",
        "CYY-CN-GRAMMAR-005",
        "CYY-CN-GRAMMAR-006",
    }.issubset(rules)


def test_chinese_human_baseline_rules_cover_format_mixed_language_and_redundancy_cases():
    content = (
        "操作步骤如下:1. 加入试剂。注意事项：a)避免污染。请勿将试剂暴露于强光下!"
        "加入 10μL Buffer，5μL Enzyme 和 2μL Primer。该步骤非常重要……请严格按照规范执行。"
        "Q: 使用\"引物\"还是'引物'？Q: PCR(Polymerase Chain Reaction) 的优化条件？"
        "记录日期：2026-07-27、2026/07/27、2026.07.27。温度控制：37°C、37℃、37 度 C。"
        "反应时间：min、分钟、mins。章节编号：1.、1）、(1)、①。温度要求 37°C 或室温。"
        "使用 RNA extraction kit 进行 RNA 提取，将 sample 加入 collection tube 中。"
        "PCR 产物通过 Agarose Gel 电泳检测。设置 thermocycler 程序。使用 ddH2O 配制溶液。OD260/OD280 比值应在 1.8-2.0 之间。"
        "该试剂盒仅供科研使用，不得用于临床诊断。"
        "操作过程中应注意安全，注意安全事项，确保安全操作。"
        "结果判读：根据说明书中的结果判读方法进行判读。"
    )

    issues = review_api._run_chinese_human_baseline_rules(content)
    originals = {issue["original_text"] for issue in issues}
    rules = {issue["rule"] for issue in issues}

    assert {
        "如下:1.",
        "a)避免污染",
        "10μL Buffer，5μL Enzyme 和",
        "强光下!",
        "非常重要……",
        "'引物'",
        "PCR(Polymerase",
        "2026-07-27、2026/07/27、2026.07.27",
        "37°C、37℃、37 度 C",
        "min、分钟、mins",
        "1.、1）、(1)、①",
        "37°C 或室温",
        "RNA extraction kit",
        "sample",
        "collection tube",
        "Agarose Gel",
        "thermocycler",
        "ddH2O",
        "OD",
        "仅供科研使用，不得用于临床诊断",
        "应注意安全，注意安全事项，确保安全操作",
        "结果判读：根据说明书中的结果判读方法进行判读",
    }.issubset(originals)
    assert {
        "CYY-CN-PUNCT-001",
        "CYY-CN-PUNCT-002",
        "CYY-CN-PUNCT-006",
        "CYY-CN-PUNCT-003",
        "CYY-CN-PUNCT-007",
        "CYY-CN-PUNCT-004",
        "CYY-CN-PUNCT-005",
        "CYY-CN-FORMAT-001",
        "CYY-CN-FORMAT-002",
        "CYY-CN-FORMAT-003",
        "CYY-CN-FORMAT-004",
        "CYY-CN-LOGIC-001",
        "CYY-CN-MIXED-001",
        "CYY-CN-MIXED-002",
        "CYY-CN-MIXED-003",
        "CYY-CN-MIXED-004",
        "CYY-CN-MIXED-005",
        "CYY-CN-MIXED-006",
        "CYY-CN-MIXED-007",
        "CYY-CN-REDUNDANCY-001",
        "CYY-CN-REDUNDANCY-002",
        "CYY-CN-REDUNDANCY-003",
    }.issubset(rules)


def test_chinese_human_baseline_rules_cover_consistency_logic_and_product_cases():
    content = (
        "本文档详细介绍了单细胞 RNA 文库制备试剂盒套装。"
        "图1标题为流程图，图2标题为示意图。"
        "前文用 Catalog Number，后文用 Cat. No.。表格1使用 Cat.No。"
        "使用 PBMC 和外周血单个核细胞进行分析。RNA 完整性对实验结果至关重要，RNA 质量直接影响数据可靠性。"
        "表3列出了试剂盒的5个组分。步骤3要求使用试剂A进行反应。声称无 RNase 污染。"
        "货号：H-020-000898-01。规格：16 RXN / 4 RXN。"
    )

    issues = review_api._run_chinese_human_baseline_rules(content)
    originals = {issue["original_text"] for issue in issues}
    rules = {issue["rule"] for issue in issues}

    assert {
        "套装",
        "示意图",
        "Catalog Number",
        "Cat. No.",
        "外周血单个核细胞",
        "RNA 质量",
        "5个组分",
        "试剂A",
        "无 RNase 污染。",
        "H-020-000898-01",
        "RXN",
    }.issubset(originals)
    assert {
        "CYY-CN-CONSIST-003",
        "CYY-CN-CONSIST-004",
        "CYY-CN-CONSIST-005",
        "CYY-CN-CONSIST-006",
        "CYY-CN-CONSIST-007",
        "CYY-CN-LOGIC-002",
        "CYY-CN-LOGIC-003",
        "CYY-CN-LOGIC-004",
        "CYY-CN-PRODUCT-001",
        "CYY-CN-PRODUCT-002",
        "CYY-CN-PRODUCT-003",
    }.issubset(rules)


def test_chinese_human_baseline_rules_cover_spacing_figure_and_info_completeness_cases():
    content = (
        "前面试剂用量为 10 μL，后续实验使用 10μL。"
        "图1引用为图 1，展示文库制备流程。"
        "储存条件：-20°C 避光保存。警告：避免反复冻融。"
        "步骤3要求使用试剂A进行反应。操作时间约 30 分钟。"
        "保质期标注可靠，生产日期格式规范。"
    )

    issues = review_api._run_chinese_human_baseline_rules(content)
    originals = {issue["original_text"] for issue in issues}
    rules = {issue["rule"] for issue in issues}

    assert {
        "10μL",
        "图 1",
        "-20°C 避光保存。警告：避免反复冻融",
        "操作时间约 30 分钟",
        "生产日期格式规范",
        "试剂A",
    }.issubset(originals)
    assert {
        "CYY-CN-FORMAT-005",
        "CYY-CN-CONSIST-008",
        "CYY-CN-LOGIC-003",
        "CYY-CN-LOGIC-005",
        "CYY-CN-LOGIC-006",
        "CYY-CN-INFO-001",
    }.issubset(rules)


def test_known_false_positive_filter_drops_placeholder_and_duplicate_ai_items():
    ai_placeholder = {
        'original_text': '（版本号待补充）',
        'rule': '信息完整性：关键章节内容缺失',
        'source': 'ai',
        'description': '',
        'suggestion': '需补充版本号',
        'audit_basis': '',
    }
    ai_duplicate = {
        'original_text': '10μL',
        'rule': '单位规则：数字与单位之间需保留空格',
        'source': 'ai',
        'description': '',
        'suggestion': '10 μL',
        'audit_basis': '',
    }
    rule_duplicate = {
        'original_text': '用于用于',
        'rule': 'CYY-CN-DUP-002',
        'source': 'rule',
        'description': '连续重复中文词可能是复制或编辑残留。',
        'suggestion': '用于',
        'audit_basis': 'baseline',
    }

    assert review_api._should_drop_known_false_positive_issue(ai_placeholder) is True
    assert review_api._should_drop_known_false_positive_issue(ai_duplicate) is True
    assert review_api._should_drop_known_false_positive_issue(rule_duplicate) is True


def test_normalize_review_issue_display_falls_back_to_description_when_suggestion_missing():
    issue = SimpleNamespace(
        suggestion='',
        description='问题说明：术语表缺少对应中文释义',
        rule='TERM-001',
        category='术语一致性',
        chapter='1.1 Scope',
        context='',
        original_text='',
        position=None,
    )

    result = review_api._normalize_review_issue_display([issue])

    assert result[0].suggestion == '术语表缺少对应中文释义'
