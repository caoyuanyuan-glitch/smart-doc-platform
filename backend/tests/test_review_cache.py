import json
import asyncio
import re
from types import SimpleNamespace

from app.api import review as review_api
from app.api import review_rules
from app.crud import rule as crud_rule
from app.review_engine import pipeline as review_pipeline
from app.review_engine import validation as review_validation


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

    assert review_api.PROJECT_ROOT / "backend" / "app" / "crud" / "rule.py" in review_api.REVIEW_CACHE_VERSION_FILES
    assert review_api.PROJECT_ROOT / "backend" / "seed" / "review_rule_library_seed.json" in review_api.REVIEW_CACHE_VERSION_FILES


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


def test_seed_external_review_rules_updates_existing_rule(monkeypatch):
    payload = {
        "source": "外部评审规则库",
        "export_date": "2026-08-17",
        "rules": [{
            "rule_id": "R013",
            "rule_content": "标点符号使用必须符合规范",
            "category": "格式",
            "severity": "一般",
            "applicable_scenarios": ["PDF"],
        }],
    }
    existing = SimpleNamespace(
        rule_no="EXT-R013",
        category="旧分类",
        description="旧规则",
        regex="old-regex",
        example="old-example",
        suggestion="old-suggestion",
        audit_basis="old-basis",
        severity="serious",
        language="cn",
    )
    commits = []
    db = SimpleNamespace(add=lambda item: None, commit=lambda: commits.append(True))

    monkeypatch.setattr(
        crud_rule,
        "REVIEW_RULE_LIBRARY_SEED_PATH",
        SimpleNamespace(
            exists=lambda: True,
            read_text=lambda encoding="utf-8": json.dumps(payload, ensure_ascii=False),
        ),
    )
    monkeypatch.setattr(crud_rule, "get_rule_by_no", lambda db_obj, rule_no: existing if rule_no == "EXT-R013" else None)

    changed = crud_rule.seed_external_review_rules(db)

    assert changed == 1
    assert existing.description == "标点符号使用必须符合规范"
    assert existing.regex == "(?!)"
    assert existing.severity == "general"
    assert existing.language == "both"
    assert commits == [True]


def test_convert_rule_content_to_regex_disables_ui_bracket_semantic_rule():
    regex = crud_rule._convert_rule_content_to_regex(
        "仅可交互UI元素（按钮、菜单、输入框、选项等）使用【】标注，界面名称/标题（如主界面、测序界面等）不使用【】"
    )

    assert regex == "(?!)"


def test_convert_rule_content_to_regex_disables_quote_semantic_rule():
    regex = crud_rule._convert_rule_content_to_regex(
        "文档中所有需要使用引号的场景统一使用双引号，不得混用单引号"
    )

    assert regex == "(?!)"


def test_review_rules_do_not_hardcode_single_quote_or_screen_name_as_errors():
    punctuation_patterns = {rule["pattern"] for rule in review_rules.CHINESE_PUNCTUATION_RULES}
    terminology_patterns = {rule["pattern"] for rule in review_rules.CHINESE_TERMINOLOGY_RULES}

    assert r"[\u2018\u2019]" not in punctuation_patterns
    assert r"【测序界面】" not in terminology_patterns


def test_system_prompt_keeps_ui_bracket_guidance_without_forcing_screen_names():
    prompt = review_rules.SYSTEM_PROMPT_TEMPLATE

    assert "仅按钮、菜单、输入框、选项等可交互UI元素使用【】标注；界面名称和标题保持原文写法" in prompt
    assert "单引号仅在明确影响语义或格式规范时报告" in prompt


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


def test_export_review_excel_appends_red_opinion_columns(tmp_path, monkeypatch):
    from openpyxl import Workbook, load_workbook

    upload_dir = tmp_path / "uploads"
    export_dir = tmp_path / "exports"
    upload_dir.mkdir()
    export_dir.mkdir()

    workbook_path = upload_dir / "demo.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["中文", "英文"])
    ws.append(["保存", "Save"])
    wb.save(workbook_path)

    monkeypatch.setattr(review_api, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(review_api, "REVIEW_EXPORT_DIR", export_dir)
    monkeypatch.setattr(review_api, "_select_export_issues", lambda payload: payload)

    document = SimpleNamespace(filename="demo.xlsx")
    review = SimpleNamespace(id=18)
    issues = [{
        "severity": "general",
        "category": "格式问题",
        "rule": "XLS-FMT-001",
        "description": "英文译文存在连续空格。",
        "suggestion": "建议改为 Save",
        "status": "pending",
        "source": "excel",
        "confidence": 95,
        "position": review_api._encode_issue_position_with_meta(0, 0, sheet="Sheet1", row=2, source_column=1, target_column=2),
    }]

    export_path, _, _ = review_api._export_review_excel(review, document, issues)

    exported = load_workbook(export_path)
    ws = exported["Sheet1"]
    assert ws.cell(row=1, column=3).value == "审核意见"
    assert ws.cell(row=2, column=3).value == "[格式问题] 英文译文存在连续空格。 → Save"
    assert ws.cell(row=2, column=3).font.color.type == "rgb"
    assert ws.cell(row=2, column=3).font.color.rgb.endswith("FF0000")
    assert ws.cell(row=2, column=4).value == "待修改"
    assert ws.cell(row=2, column=5).value == 1


def test_generate_excel_review_html_content_groups_rows(monkeypatch):
    monkeypatch.setattr(review_api, "_format_report_datetime", lambda value=None: "2026-08-18 12:00:00 (UTC+8)")
    monkeypatch.setattr(review_api, "_select_export_issues", lambda payload: payload)
    review = SimpleNamespace(id=16, document_id=8, created_at=None, completed_at=None)
    document = SimpleNamespace(filename="demo.xlsx", file_type="xlsx")
    issues = [
        {
            "severity": "serious",
            "category": "完整性",
            "rule": "XLS-COMP-002",
            "description": "英文译文为空，需补充。",
            "suggestion": "补充英文译文",
            "context": "中文: 保存 | 英文: ",
            "status": "pending",
            "source": "excel",
            "confidence": 95,
            "position": review_api._encode_issue_position_with_meta(0, 0, sheet="Sheet1", row=2, source_column=1, target_column=2),
        }
    ]

    html = review_api._generate_excel_review_html_content(review, document, issues)

    assert "Excel 审核报告" in html
    assert "Sheet1 / 第 2 行" in html
    assert "英文译文为空，需补充。 → 补充英文译文" in html
    assert "命中行数" in html


def test_run_excel_review_audit_covers_manual_excel_findings(tmp_path, monkeypatch):
    from openpyxl import Workbook

    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    workbook_path = upload_dir / "manual-gap.xlsx"

    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["中文", "英文"])
    ws.append(["系统设置", "System Settings"])
    ws.append(["长按3s启动", "Press and hold for 3s to start"])
    ws.append(["锁屏时间", "Lock Screen Timeout Period"])
    ws.append(["时间日期   ", "Date&Time"])
    ws.append(["目标速度-", "Target Speed"])
    ws.append(["目标角度-", "Traget Angle"])
    ws.append(["错误信息", "Error message"])
    ws.append(["确认恢复出厂设置", "Confirm factory reset?"])
    ws.append(["确认固件升级", "Confirm to start firmware upgrade?"])
    ws.append(["确认结束老化测试", "Confirm to end aging test?"])
    ws.append(["确认清除老化次数", "Confirm to clear aging count?"])
    ws.append(["语言设置", "Language"])
    wb.save(workbook_path)

    monkeypatch.setattr(review_api, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(review_api, "get_terms", lambda db, limit=10000: [])

    issues = review_api._run_excel_review_audit(None, SimpleNamespace(filename="manual-gap.xlsx"))

    original_texts = {issue["original_text"] for issue in issues}
    rules = {issue["rule"] for issue in issues}
    pair_002_issue = next(issue for issue in issues if issue["rule"] == "XLS-PAIR-002")

    assert "System Settings" not in original_texts
    assert "Press and hold for 3s to start" not in original_texts
    assert "Traget Angle" in original_texts
    assert "Confirm to start firmware upgrade?" in original_texts
    assert "Confirm to end aging test?" in original_texts
    assert "Confirm to clear aging count?" in original_texts
    assert pair_002_issue["suggestion"] == "建议改为 Screen Timeout"
    assert "XLS-CN-FMT-001" in rules
    assert "XLS-CN-FMT-002" in rules
    assert "XLS-PUNCT-001" in rules
    assert "XLS-PAIR-001" in rules
    assert "XLS-EN-STYLE-002" in rules
    assert "XLS-LANG-003" in rules


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


def test_build_ai_review_basis_sections_include_structured_cyy_sections(monkeypatch):
    monkeypatch.setattr(
        review_api,
        "_load_cyy_human_review_basis_sections",
        lambda: [
            {"label": "CYY人工审核经验基线摘要", "text": "【CYY人工审核经验基线摘要】\n总览", "priority": 5},
            {"label": "CYY人工审核经验基线-步骤结构", "text": "【CYY人工审核经验基线 - 步骤结构】\n关注步骤缺失", "priority": 5},
        ],
    )

    sections = review_api._build_ai_review_basis_sections({}, "cn")
    labels = [section["label"] for section in sections]

    assert "CYY人工审核经验基线摘要" in labels
    assert "CYY人工审核经验基线-步骤结构" in labels


def test_load_cyy_human_review_basis_sections_omits_comment_details(monkeypatch):
    review_api.CYY_HUMAN_REVIEW_BASIS_SECTIONS_CACHE = None
    monkeypatch.setattr(
        review_api,
        "CYY_HUMAN_REVIEW_BASELINE_PATH",
        SimpleNamespace(
            exists=lambda: True,
            read_text=lambda encoding="utf-8": json.dumps(
                {
                    "summary": {"total": 2, "by_category": {"步骤结构": 2}},
                    "annotations": [{"category": "步骤结构", "comment": "步骤3之后直接跳到步骤5"}],
                },
                ensure_ascii=False,
            ),
        ),
    )

    sections = review_api._load_cyy_human_review_basis_sections()

    assert any(section["label"] == "CYY人工审核经验基线-步骤结构" for section in sections)
    assert all("步骤3之后直接跳到步骤5" not in section["text"] for section in sections)


def test_select_relevant_ai_review_basis_prefers_matching_cyy_category_sections():
    sections = [
        {"label": "CYY人工审核经验基线摘要", "text": "【CYY人工审核经验基线摘要】\n关注高频问题。", "priority": 5},
        {"label": "CYY人工审核经验基线-步骤结构", "text": "【CYY人工审核经验基线 - 步骤结构】\n步骤编号跳号、步骤缺失、操作不可执行。", "priority": 5},
        {"label": "CYY人工审核经验基线-版本记录", "text": "【CYY人工审核经验基线 - 版本记录】\nrevision history 版本记录 日期。", "priority": 4},
    ]

    selected = review_api._select_relevant_ai_review_basis(
        "步骤3之后直接跳到步骤5，导致操作步骤缺失。",
        sections,
        max_sections=2,
        char_budget=500,
    )

    assert "步骤结构" in selected
    assert "操作不可执行" in selected


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


def test_pipeline_filters_single_char_punctuation_rule_issue():
    issues = [
        {
            "source": "rule",
            "rule": "EXT-R013",
            "category": "格式错误",
            "severity": "general",
            "original_text": ".",
            "suggestion": "文档中标点符号使用必须符合规范",
            "description": "单字符标点噪声",
            "audit_basis": "标点规范",
        }
    ]

    selected = review_pipeline.select_review_issues(issues)

    assert selected == []


def test_pipeline_filters_quote_rule_without_quote_evidence():
    issues = [
        {
            "source": "rule",
            "rule": "EXT-R011",
            "category": "格式错误",
            "severity": "general",
            "original_text": "不能",
            "context": "A 不能。盘点状态下的物料将被系统锁定。",
            "suggestion": "文档中所有需要使用引号的场景统一使用双引号，不得混用单引号",
            "description": "文档中所有需要使用引号的场景统一使用双引号，不得混用单引号",
            "audit_basis": "引号规范",
        }
    ]

    selected = review_pipeline.select_review_issues(issues)

    assert selected == []


def test_pipeline_keeps_serious_real_spelling_issue():
    issues = [
        {
            "source": "spellcheck",
            "rule": "SPELL",
            "category": "拼写/用词错误",
            "severity": "serious",
            "original_text": "consumbles",
            "suggestion": "consumables",
            "description": "拼写错误",
            "audit_basis": "英文拼写规范",
            "confidence": 96,
        }
    ]

    selected = review_pipeline.select_review_issues(issues)

    assert len(selected) == 1
    assert selected[0]["original_text"] == "consumbles"


def test_should_drop_unicode_equivalent_issue_accepts_mu_variants():
    issue = {
        "original_text": "20 µL",
        "suggestion": "20 μL",
    }

    assert review_api._should_drop_unicode_equivalent_issue(issue) is True


def test_run_logic_integrity_audit_skips_mixed_separator_false_positive():
    content = "4) Load sample\n12. Secondary heading\n"

    issues = review_api._run_logic_integrity_audit(content)

    assert not any(issue.get("rule") == "LOGIC-001" for issue in issues)


def test_dedupe_issues_by_original_prefers_spellcheck_over_ai():
    ai_issue = {
        "severity": "serious",
        "category": "语法",
        "rule": "AI-GRAMMAR",
        "chapter": "Section 1",
        "original_text": "Reviewing parameters",
        "source": "ai",
        "confidence": 95,
        "position": "10-30",
    }
    spell_issue = {
        "severity": "general",
        "category": "拼写/用词错误",
        "rule": "SPELL",
        "chapter": "Section 1",
        "original_text": "Reviewing parameters",
        "source": "spellcheck",
        "confidence": 80,
        "position": "10-30",
    }

    deduped = review_api.dedupe_issues_by_original([ai_issue, spell_issue])

    assert len(deduped) == 1
    assert deduped[0]["source"] == "spellcheck"


def test_dedupe_issues_by_original_prefers_spellcheck_when_chapter_differs_but_suggestion_matches():
    ai_issue = {
        "severity": "general",
        "category": "Terminology",
        "rule": "AI-TERM",
        "chapter": "Section 2.2 User-supplied equipment, reagent, and consumbles",
        "original_text": "consumbles",
        "suggestion": "consumables",
        "source": "ai",
        "confidence": 100,
        "position": "2898-2908",
    }
    spell_issue = {
        "severity": "general",
        "category": "拼写/用词错误",
        "rule": "SPELL",
        "chapter": "2.2 User-supplied equipment, reagent, and",
        "original_text": "consumbles",
        "suggestion": "consumables",
        "source": "spellcheck",
        "confidence": 95,
        "position": "2898-2908",
    }

    deduped = review_api.dedupe_issues_by_original([ai_issue, spell_issue])

    assert len(deduped) == 1
    assert deduped[0]["source"] == "spellcheck"


def test_validate_ai_issue_candidate_rejects_ruo_template_rewrite():
    issue = {
        "source": "ai",
        "original_text": "WARNING This product is intended only for scientific research and should not be used for clinical diagnosis.",
        "suggestion": "WARNING: This product is for research use only (RUO) and is not intended for clinical diagnostic use.",
        "description": "",
        "rule": "Compliance",
        "chapter": "Warnings",
        "audit_basis": "basis",
    }
    content = issue["original_text"]

    result = review_validation.validate_ai_issue_candidate(issue, content)

    assert result.accepted is False
    assert result.reason == "protected_meaning_changed"


def test_validate_ai_issue_candidate_rejects_dnb_expansion_rewrite():
    issue = {
        "source": "ai",
        "original_text": "The device adopts the advanced DNB and the core technology of combinatorial probe-anchor synthesis (cPAS)",
        "suggestion": "The system uses DNA Nanoballs (DNBs) and the core technology of combinatorial probe-anchor synthesis (cPAS)",
        "description": "",
        "rule": "Terminology",
        "chapter": "Introduction",
        "audit_basis": "basis",
    }
    content = issue["original_text"]

    result = review_validation.validate_ai_issue_candidate(issue, content)

    assert result.accepted is False
    assert result.reason == "protected_meaning_changed"


def test_validate_ai_issue_candidate_rejects_article_only_rewrite():
    issue = {
        "source": "ai",
        "original_text": "ensure that proper protections for personnel and device are implemented to avoid contamination by sequencing reagents.",
        "suggestion": "Ensure that proper protections for personnel and the device are implemented to avoid contamination by sequencing reagents.",
        "description": "",
        "rule": "Operation",
        "chapter": "CAUTION",
        "audit_basis": "basis",
    }
    content = issue["original_text"]

    result = review_validation.validate_ai_issue_candidate(issue, content)

    assert result.accepted is False
    assert result.reason == "low_value_english_rewrite"


def test_validate_ai_issue_candidate_rejects_dnb_solution_expansion_rewrite():
    issue = {
        "source": "ai",
        "original_text": "DNB 102",
        "suggestion": "DNB solution 102",
        "description": "",
        "rule": "Table",
        "chapter": "Table 3",
        "audit_basis": "basis",
    }
    content = "Table 3 includes DNB 102 in the component list."

    result = review_validation.validate_ai_issue_candidate(issue, content)

    assert result.accepted is False
    assert result.reason == "protected_meaning_changed"


def test_validate_ai_issue_candidate_rejects_speculative_completion():
    issue = {
        "source": "ai",
        "original_text": "Add 34 µL of",
        "suggestion": "Add 34 µL of DNB loading mixture.",
        "description": "",
        "rule": "Operation",
        "chapter": "Step 5",
        "audit_basis": "basis",
    }
    content = "Then add 34 µL of to the tube for the next step."

    result = review_validation.validate_ai_issue_candidate(issue, content)

    assert result.accepted is False
    assert result.reason == "speculative_completion"


def test_validate_ai_issue_candidate_rejects_speculative_completion_with_bullet_prefix():
    issue = {
        "source": "ai",
        "original_text": "y If a reagent cartridge has been",
        "suggestion": "If a reagent cartridge has been thawed and the signal protein mixture has been added into the MSP well according to Preparing the reagent cartridge on Page 18, but it cannot be used in time, store it at room temperature and use it within 2 hours.",
        "description": "",
        "rule": "Completeness",
        "chapter": "Storage",
        "audit_basis": "basis",
    }
    content = "y If a reagent cartridge has been"

    result = review_validation.validate_ai_issue_candidate(issue, content)

    assert result.accepted is False
    assert result.reason == "speculative_completion"


def test_aggressive_rewrite_blocks_template_rewrites():
    assert review_validation.ai_suggestion_is_aggressive_rewrite(
        "This reagent set is for research use only, and cannot be used for clinical diagnosis.",
        "This reagent set is for research use only (RUO) and is not intended for clinical diagnosis, patient management, or any diagnostic purposes.",
    ) is True
    assert review_validation.ai_suggestion_is_aggressive_rewrite(
        "This product is for research use only. Please read the instructions for use of the product carefully before use.",
        "This product is for research use only (RUO).",
    ) is True
    assert review_validation.ai_suggestion_is_aggressive_rewrite(
        "The reagent cartridge is completely thawed when there is no sound of cracked ice during shaking.",
        "The reagent cartridge is completely thawed when no sound of cracking ice is heard during gentle shaking.",
    ) is True


def test_aggressive_rewrite_passes_local_fixes():
    assert review_validation.ai_suggestion_is_aggressive_rewrite(
        "This instructions for use describes how to perform sequencing",
        "These instructions for use describe how to perform sequencing",
    ) is False
    assert review_validation.ai_suggestion_is_aggressive_rewrite(
        "Disgestive Buffer 250 uL per tube",
        "Digestive Buffer 250 uL per tube",
    ) is False
    assert review_validation.ai_suggestion_is_aggressive_rewrite(
        "click OK, The device begins unloading",
        "Tap OK, The device begins unloading",
    ) is False


def test_validate_ai_issue_candidate_accepts_local_grammar_fix():
    issue = {
        "source": "ai",
        "original_text": "This instructions for use describes how to perform sequencing",
        "suggestion": "These instructions for use describe how to perform sequencing",
        "description": "",
        "rule": "Grammar",
        "chapter": "Introduction",
        "audit_basis": "basis",
    }

    result = review_validation.validate_ai_issue_candidate(issue, issue["original_text"])

    assert result.accepted is True
    assert result.reason == "accepted"


def test_validate_ai_issue_candidate_accepts_digestive_spelling_fix():
    issue = {
        "source": "ai",
        "original_text": "Disgestive Buffer 250 uL per tube",
        "suggestion": "Digestive Buffer 250 uL per tube",
        "description": "",
        "rule": "Spelling",
        "chapter": "Reagents",
        "audit_basis": "basis",
    }

    result = review_validation.validate_ai_issue_candidate(issue, issue["original_text"])

    assert result.accepted is True
    assert result.reason == "accepted"


def test_validate_ai_issue_candidate_rejects_high_overlap_style_rewrite():
    issue = {
        "source": "ai",
        "original_text": "Data output (GB/flow cell)",
        "suggestion": "Data output (GB per flow cell)",
        "description": "",
        "rule": "Terminology",
        "chapter": "Specifications",
        "audit_basis": "basis",
    }
    content = "The specification table contains Data output (GB/flow cell)."

    result = review_validation.validate_ai_issue_candidate(issue, content)

    assert result.accepted is False
    assert result.reason == "low_value_english_rewrite"


def test_validate_ai_issue_candidate_rejects_support_policy_rewrite():
    issue = {
        "source": "ai",
        "original_text": "For the username and password, contact the technical support.",
        "suggestion": "Default credentials are not provided. Contact technical support to obtain authorized login credentials.",
        "description": "",
        "rule": "Operation",
        "chapter": "Login",
        "audit_basis": "basis",
    }
    content = issue["original_text"]

    result = review_validation.validate_ai_issue_candidate(issue, content)

    assert result.accepted is False
    assert result.reason == "protected_meaning_changed"


def test_validate_ai_issue_candidate_rejects_instructions_for_use_semantic_rewrite():
    issue = {
        "source": "ai",
        "original_text": "The instructions for use are provided in the package.",
        "suggestion": "The IFU is provided in the package.",
        "description": "",
        "rule": "Terminology",
        "chapter": "Introduction",
        "audit_basis": "basis",
    }

    result = review_validation.validate_ai_issue_candidate(issue, issue["original_text"])

    assert result.accepted is False
    assert result.reason == "protected_meaning_changed"


def test_validate_ai_issue_candidate_rejects_mixedly_use_rewrite():
    issue = {
        "source": "ai",
        "original_text": "Do not mixedly use the MDA T-Regent from different models of reagent kits.",
        "suggestion": "Do not mix the MDA T-Reagent from different reagent kit models.",
        "description": "",
        "rule": "Terminology",
        "chapter": "Tips",
        "audit_basis": "basis",
    }

    result = review_validation.validate_ai_issue_candidate(issue, issue["original_text"])

    assert result.accepted is False
    assert result.reason == "protected_meaning_changed"


def test_validate_ai_issue_candidate_rejects_app_library_pluralization_rewrite():
    issue = {
        "source": "ai",
        "original_text": "For App library",
        "suggestion": "For App libraries",
        "description": "",
        "rule": "Terminology",
        "chapter": "4.4 Quantifying DNBs",
        "audit_basis": "basis",
    }

    result = review_validation.validate_ai_issue_candidate(issue, issue["original_text"])

    assert result.accepted is False
    assert result.reason == "protected_meaning_changed"


def test_validate_ai_issue_candidate_rejects_choose_scheme_semantic_rewrite():
    issue = {
        "source": "ai",
        "original_text": "y The recipe you selected should be consistent with the selected type in the Choose scheme interface.",
        "suggestion": "The recipe you selected must match the assay type selected in the Choose scheme interface.",
        "description": "",
        "rule": "Terminology",
        "chapter": "Tips",
        "audit_basis": "basis",
    }

    result = review_validation.validate_ai_issue_candidate(issue, issue["original_text"])

    assert result.accepted is False
    assert result.reason == "protected_meaning_changed"


def test_validate_ai_issue_candidate_rejects_local_regulations_compliance_expansion():
    issue = {
        "source": "ai",
        "original_text": "y Dispose of the flow cell, reagent cartridge, waste, waste container, and PCR tube in accordance with local regulations and safety standards.",
        "suggestion": "Dispose of the flow cell, reagent cartridge, waste, waste container, and PCR tube in accordance with applicable local, national, and institutional biosafety and hazardous waste regulations.",
        "description": "",
        "rule": "Compliance",
        "chapter": "7.7 Removing the flow cell, reagent cartridge, and waste container",
        "audit_basis": "basis",
    }

    result = review_validation.validate_ai_issue_candidate(issue, issue["original_text"])

    assert result.accepted is False
    assert result.reason == "protected_meaning_changed"


def test_validate_ai_issue_candidate_rejects_split_barcode_default_value_expansion():
    issue = {
        "source": "ai",
        "original_text": "If the selected recipe includes the barcode length, you need to select whether to split barcode.",
        "suggestion": "If the selected recipe includes a barcode, select whether to split the barcode. 'Yes' is selected by default.",
        "description": "",
        "rule": "Clarity",
        "chapter": "step 5",
        "audit_basis": "basis",
    }

    result = review_validation.validate_ai_issue_candidate(issue, issue["original_text"])

    assert result.accepted is False
    assert result.reason == "protected_meaning_changed"


def test_validate_ai_issue_candidate_rejects_flow_cell_validation_logic_expansion():
    issue = {
        "source": "ai",
        "original_text": "Scan the QR code on the plastic package of the sequencing flow cell. Flow cell ID, Throughput, and Expiration date are automatically filled in.",
        "suggestion": "Scan the QR code on the plastic package of the sequencing flow cell. Flow cell ID, Throughput, and Expiration date are automatically filled in. If the flow cell ID is invalid or expired, the system displays an error and prevents proceeding.",
        "description": "",
        "rule": "Completeness",
        "chapter": "step 7.3, item 1",
        "audit_basis": "basis",
    }

    result = review_validation.validate_ai_issue_candidate(issue, issue["original_text"])

    assert result.accepted is False
    assert result.reason == "protected_meaning_changed"


def test_validate_ai_issue_candidate_rejects_reagent_pluralization_inside_faulty_title():
    issue = {
        "source": "ai",
        "original_text": "reagent",
        "suggestion": "reagents",
        "description": "",
        "rule": "Terminology",
        "chapter": "2.2 User-supplied equipment, reagent, and consumbles",
        "audit_basis": "basis",
    }
    content = "2.2 User-supplied equipment, reagent, and consumbles"

    result = review_validation.validate_ai_issue_candidate(issue, content)

    assert result.accepted is False
    assert result.reason == "protected_meaning_changed"


def test_validate_ai_issue_candidate_rejects_dnb_rationale_completion():
    issue = {
        "source": "ai",
        "original_text": "Do not centrifuge, vortex, or shake the tube.",
        "suggestion": "Do not centrifuge, vortex, or shake the tube — these actions may shear or aggregate DNBs.",
        "description": "",
        "rule": "Completeness",
        "chapter": "Tips under Step 3",
        "audit_basis": "basis",
    }

    result = review_validation.validate_ai_issue_candidate(issue, issue["original_text"])

    assert result.accepted is False
    assert result.reason == "protected_meaning_changed"


def test_validate_ai_issue_candidate_rejects_visual_icon_gap_from_pdf_text_loss():
    issue = {
        "source": "ai",
        "original_text": "双击计算机桌面软件图标 启动操作软件。",
        "suggestion": "请补充需要双击的具体软件图标名称，避免仅写图标。",
        "description": "操作步骤缺少具体图标对象，用户无法确定点击哪个图标。",
        "rule": "Completeness",
        "category": "操作步骤",
        "chapter": "开机与软件准备",
        "audit_basis": "basis",
        "context": "4. 先按计算机电源按钮开机，再按仪器电源开关，启动仪器。5. 双击计算机桌面软件图标 启动操作软件。6. 等待软件完成自检流程。",
    }

    result = review_validation.validate_ai_issue_candidate(issue, issue["context"])

    assert result.accepted is False
    assert result.reason == "visual_control_ambiguity"


def test_validate_ai_issue_candidate_rejects_visual_button_gap_from_pdf_text_loss():
    issue = {
        "source": "ai",
        "original_text": "点击采集模式后方的 按钮，可设置模式参数。",
        "suggestion": "请补充该按钮或图标的具体名称，避免用户无法定位。",
        "description": "操作步骤缺少具体按钮对象。",
        "rule": "Completeness",
        "category": "操作步骤",
        "chapter": "采集模式",
        "audit_basis": "basis",
        "context": "实时显示眼底图像。点击采集模式后方的 按钮，可设置模式参数。显示相应眼别的采集任务。",
    }

    result = review_validation.validate_ai_issue_candidate(issue, issue["context"])

    assert result.accepted is False
    assert result.reason == "visual_control_ambiguity"


def test_validate_ai_issue_candidate_keeps_true_missing_ui_object_issue():
    issue = {
        "source": "ai",
        "original_text": "点击【仓库标签】行的,弹出仓库标签编辑窗口。",
        "suggestion": "点击【仓库标签】行末【操作】栏的【编辑】图标，弹出仓库标签编辑窗口。",
        "description": "操作步骤缺少具体操作对象，无法确定点击位置。",
        "rule": "Completeness",
        "category": "操作步骤",
        "chapter": "仓库标签",
        "audit_basis": "basis",
        "context": "字典管理 > 仓库标签。点击【仓库标签】行的,弹出仓库标签编辑窗口。",
    }

    result = review_validation.validate_ai_issue_candidate(issue, issue["context"])

    assert result.accepted is True
    assert result.reason == "accepted"


def test_run_english_heuristic_audit_detects_this_instructions_grammar_issue():
    issues = review_api._run_english_heuristic_audit(
        "This instructions for use describes how to perform sequencing.",
        file_type="pdf",
    )

    assert any(issue.get("rule") == "GRAMMAR-007" for issue in issues)


def test_run_english_heuristic_audit_keeps_official_global_site():
    issues = review_api._run_english_heuristic_audit(
        "For more information, visit https://global-mgitech.com/ for the latest manuals.",
        file_type="pdf",
    )

    assert not any(issue.get("rule") in {"HR001", "HR012"} for issue in issues)


def test_review_ai_chunk_timeout_seconds_uses_higher_default_for_large_chunks(monkeypatch):
    monkeypatch.delenv("REVIEW_AI_CHUNK_TIMEOUT", raising=False)

    timeout = review_api._review_ai_chunk_timeout_seconds("A" * 3000)

    assert timeout == 35.0


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


def test_review_ai_chunk_limit_defaults_to_ten(monkeypatch):
    monkeypatch.delenv("REVIEW_AI_MAX_CHUNKS", raising=False)

    assert review_api._review_ai_chunk_limit() == 10


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


def test_chinese_human_baseline_rules_cover_alpha_lab_manual_gaps():
    content = (
        "需先选择标准计量单位，再选择包装单位及转化系数。例如：标准计量单位选‘个’，包装单位选‘箱’且转换系数设为10。"
        "首次登录前点击【图标】打开弹窗确认服务地址和机构。具体操作，参考第31页‘设置服务器地址和机构代码’。"
        "在左侧菜单栏点击【系统管理】。其余步骤写为在左侧导航栏点击【角色管理】。"
        "Q：如何区分同步物料与自增物料？A：系统支持手动新增普通物料。"
        "图59图注为修改密码界面，正文步骤均写为重置密码。"
        "处理器：X86 架构，8核及以上。默认安装在C盘，可点击【Browse】可选择目标安装目录。"
        "按照界面指引，拖拽αLab Studio 软件图标到右侧的Application 文件夹进行安装。安装完成后，点击【Install】开始安装系统，点击【Finish】完成安装。"
    )

    issues = review_api._run_chinese_human_baseline_rules(content)
    originals = {issue["original_text"] for issue in issues}
    rules = {issue["rule"] for issue in issues}

    assert {
        "转化系数",
        "服务地址",
        "左侧菜单栏",
        "自增物料",
        "修改密码界面",
        "X86 架构",
        "可点击【Browse】可选择",
    }.issubset(originals)
    assert any("【Install】" in issue["original_text"] and "【Finish】" in issue["original_text"] for issue in issues)
    assert {
        "CYY-CN-CONSIST-009",
        "CYY-CN-CONSIST-010",
        "CYY-CN-CONSIST-011",
        "CYY-CN-CONSIST-012",
        "CYY-CN-CONSIST-013",
        "CYY-CN-TERM-005",
        "CYY-CN-GRAMMAR-007",
        "CYY-CN-LOGIC-007",
    }.issubset(rules)


def test_chinese_human_baseline_rules_detect_adjacent_duplicate_steps():
    content = (
        "14. 核对入库信息。"
        "15. 在入库定位界面右侧选择目标库位，左侧填写待分配物料数量，点击【保存】，回到入库定位页签。"
        "16. 在入库定位界面左侧填写待分配物料数量，点击【保存】，回到入库定位页签。"
        "17. 继续下一步操作。"
    )

    issues = review_api._run_chinese_human_baseline_rules(content)
    assert any(issue["rule"] == "CYY-CN-STRUCT-001" for issue in issues)
    assert any("步骤 15 和步骤 16" in issue["suggestion"] for issue in issues if issue["rule"] == "CYY-CN-STRUCT-001")


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


def test_known_false_positive_filter_drops_official_global_site_issue():
    issue = {
        'original_text': 'https://global-mgitech.com/',
        'rule': 'EXT-R005',
        'source': 'ai',
        'description': '海外官网地址应统一。',
        'suggestion': '建议替换为 https://global-mgitech.com/',
        'audit_basis': '公司特定规范 - 海外官网地址',
        'context': 'For more information, visit https://global-mgitech.com/ for the latest manuals.',
    }

    assert review_api._should_drop_known_false_positive_issue(issue) is True


def test_should_skip_rule_match_skips_ext_r013_for_pdf():
    rule = SimpleNamespace(rule_no="EXT-R013")
    match = next(re.finditer(r"\.", "Overview."))

    assert review_api._should_skip_rule_match(rule, match, "Overview.", "en", file_type="pdf") is True


def test_should_drop_punctuation_issue_drops_generic_single_punctuation_noise():
    issue = {
        'original_text': '。',
        'rule': 'PUNCT-001',
        'source': 'rule',
        'suggestion': '文档中标点符号使用必须符合规范，不得遗漏必要的标点（逗号、句号等）',
        'description': '英文文档中不应混入全角或中文标点。',
        'context': 'Overview。',
    }

    assert review_api._should_drop_punctuation_issue(issue) is True


def test_prepare_report_issues_filters_generic_punctuation_noise_before_aggregation():
    issues = [
        {
            'original_text': '。',
            'rule': 'PUNCT-001',
            'source': 'rule',
            'suggestion': '文档中标点符号使用必须符合规范，不得遗漏必要的标点（逗号、句号等）',
            'description': '英文文档中不应混入全角或中文标点。',
            'context': 'Overview。',
            'position': '10-11',
            'status': 'open',
        },
        {
            'original_text': '，',
            'rule': 'PUNCT-001',
            'source': 'rule',
            'suggestion': '文档中标点符号使用必须符合规范，不得遗漏必要的标点（逗号、句号等）',
            'description': '英文文档中不应混入全角或中文标点。',
            'context': 'Scope，',
            'position': '20-21',
            'status': 'open',
        },
    ]

    prepared = review_api._prepare_report_issues(issues, 'Overview。 Scope，')

    assert prepared == []


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
