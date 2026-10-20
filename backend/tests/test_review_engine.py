"""审核逻辑修改方案（P0-P2）的回归测试。

每个用例验证最终输出（select_review_issues / review 接口后处理结果），
而不是仅验证中间函数的返回值。
"""
import json

from app.api import review as review_api
from app.review_engine import pipeline
from app.review_engine.pipeline import select_review_issues
from app.utils.ai_client import AIClient


def test_ai_english_grammar_issue_not_filtered_as_noise():
    issues = [{
        "source": "ai",
        "rule": "GRAMMAR",
        "category": "Grammar",
        "severity": "general",
        "original_text": "The samples was placed",
        "context": "The samples was placed into the tube.",
        "suggestion": "The samples were placed",
        "description": "主谓不一致：复数主语需用 were",
        "confidence": 90,
    }]
    selected = select_review_issues(issues)
    assert len(selected) == 1
    assert str(selected[0].get("source")) == "ai"


def test_ai_chinese_punctuation_issue_not_killed_by_low_value_pattern():
    issues = [{
        "source": "ai",
        "rule": "AI",
        "category": "标点",
        "severity": "general",
        "original_text": "该句为说明性短语，不应以句号结尾，标点使用不一致",
        "context": "放置载片阶段。",
        "suggestion": "删除句末句号",
        "description": "说明性短语不应以句号结尾，标点使用不一致",
        "confidence": 90,
    }]
    selected = select_review_issues(issues)
    assert len(selected) == 1
    assert "标点" in str(selected[0].get("original_text"))


def test_low_value_pattern_no_bare_chinese_token():
    pattern = pipeline.LOW_VALUE_PATTERN.pattern
    for token in ("标点", "普通语法", "冠词", "格式微调"):
        assert token not in pattern, f"LOW_VALUE_PATTERN 不应包含裸中文词: {token}"


def test_semantic_suggestion_issue_survives_pipeline():
    # P3 语义维度（冗余/语气等）多为 suggestion，须与 P0-B 白名单联用才不会被阈值丢弃
    issues = [{
        "source": "ai",
        "rule": "AI",
        "category": "冗余",
        "severity": "suggestion",
        "original_text": "关于本指南，本手册介绍了 G99 系统的操作方法。",
        "context": "关于本指南，本手册介绍了 G99 系统的操作方法。",
        "suggestion": "删除",
        "description": "无信息量引导语，可整体删除",
        "confidence": 80,
    }]
    selected = select_review_issues(issues)
    assert len(selected) == 1
    assert str(selected[0].get("category")) == "冗余"


def test_pdf_text_issue_bypasses_visual_verification():
    text_issue = {
        "source": "ai",
        "category": "术语",
        "rule": "AI",
        "description": "术语不一致",
    }
    assert review_api._should_visual_verify_issue(text_issue, "pdf") is False

    visual_issue = {
        "source": "ai",
        "category": "表格/版式",
        "rule": "AI",
        "description": "表格列宽分布不均",
    }
    assert review_api._should_visual_verify_issue(visual_issue, "pdf") is True


def test_visual_provider_unavailable_does_not_block_text_issue(monkeypatch):
    document = type("Doc", (), {"file_type": "pdf", "filename": "demo.pdf"})()
    text_issue = {
        "source": "ai",
        "severity": "general",
        "category": "术语",
        "rule": "AI",
        "original_text": "注册手册号",
        "context": "输入注册手册号后继续。",
        "description": "疑似术语错误",
        "suggestion": "改为注册手机号",
        "position": json.dumps({"page_number": 2}, ensure_ascii=False),
    }
    suspicious_pages = {
        "enabled": True,
        "candidate_count": 1,
        "candidates": [{
            "page_number": 3,
            "reasons": ["table_layout"],
            "text_preview": "版本记录 日期 版本 修订",
        }],
    }

    monkeypatch.setattr(review_api, "_review_pdf_visual_verify_enabled", lambda: True)
    monkeypatch.setattr(review_api, "_review_pdf_visual_verify_limit", lambda: 6)
    monkeypatch.setattr(review_api, "_visual_provider_available", lambda name: False)
    monkeypatch.setattr(review_api, "set_progress", lambda *args, **kwargs: None)

    filtered, diagnostics = review_api._apply_pdf_visual_verification(
        123, document, "dummy", [text_issue], suspicious_pages
    )

    assert diagnostics["reason"] == "provider_unavailable"
    assert text_issue in filtered
    assert text_issue.get("status") != "blocked"


def test_ai_summary_reports_partial_coverage():
    trace = {
        "enabled": True,
        "selected_chunk_count": 3,
        "total_chunk_count": 5,
        "chunk_meta": [
            {"cache_hit": True, "status": "ok"},
            {"status": "timeout"},
            {"status": "ok"},
        ],
    }
    summary = review_api._build_review_execution_summary(
        "hybrid", "deepseek", trace, 3, False, "", False
    )
    assert summary["full_document_reviewed"] is False
    assert summary["partial_coverage"] is True
    assert summary["cache_hits"] == 1
    assert summary["coverage_ratio"] < 1.0

    degraded = review_api._build_review_execution_summary(
        "ai", None, {"enabled": False}, 0, True, "no provider", False
    )
    assert degraded["full_document_reviewed"] is False
    assert degraded["ai_degraded"] is True
    assert degraded["ai_degraded_reason"] == "no provider"

    # provider 不可用时调用会静默返回空结果，覆盖率为 0，不能按"已处理分块"计入
    silent_failure = review_api._build_review_execution_summary(
        "hybrid", "", {"enabled": True, "selected_chunk_count": 10, "total_chunk_count": 10,
                       "chunk_meta": [{} for _ in range(10)]},
        0, True, "AI provider 未完成有效调用", False,
    )
    assert silent_failure["coverage_ratio"] == 0.0
    assert silent_failure["processed_chunks"] == 0
    assert silent_failure["full_document_reviewed"] is False


def test_pdf_whitespace_normalized_evidence_match():
    client = AIClient.__new__(AIClient)
    issues = client.normalize_audit_issues(
        [{
            "original": "The sample was placed\ninto the tube",
            "expected": "The sample was placed into the tube",
            "description": "换行导致的断裂",
            "confidence": 88,
            "severity": "general",
            "category": "格式",
        }],
        "The sample was placed\ninto\nthe tube before incubation.",
    )
    assert len(issues) == 1
    assert issues[0]["evidence_match_method"] == "normalized_whitespace"


def test_force_rerun_bypasses_ai_chunk_cache(monkeypatch):
    calls = []

    def fake_audit_document(chunk, *args, **kwargs):
        calls.append(chunk)
        return {"issues": [{"original": "x", "suggestion": "y", "description": "desc"}]}

    monkeypatch.setattr(review_api.ai_client, "audit_document", fake_audit_document)
    monkeypatch.setattr(review_api, "_ensure_review_not_cancelled", lambda review_id: None)
    monkeypatch.setattr(review_api, "_record_review_observations", lambda review_id, observations: None)

    review_id = 990001
    review_api._review_force_rerun_ids.discard(review_id)
    review_api._ai_review_chunk_cache.clear()
    try:
        chunk = "unique cache test chunk"
        first, first_hit = review_api._run_cached_ai_chunk_review(
            review_id, chunk, "zh", "basis", 5
        )
        assert first_hit is False
        assert len(calls) == 1

        second, second_hit = review_api._run_cached_ai_chunk_review(
            review_id, chunk, "zh", "basis", 5
        )
        assert second_hit is True
        assert len(calls) == 1

        review_api._review_force_rerun_ids.add(review_id)
        third, third_hit = review_api._run_cached_ai_chunk_review(
            review_id, chunk, "zh", "basis", 5
        )
        assert third_hit is False
        assert len(calls) == 2
    finally:
        review_api._review_force_rerun_ids.discard(review_id)
        review_api._ai_review_chunk_cache.clear()


def test_english_grammar_verifiable_not_penalized():
    """英文 Grammar confidence=80 的可验证文本问题不应被 value_score 压死。"""
    from app.review_engine.pipeline import value_score, is_noise, is_verifiable_ai_text_issue
    issue = {
        "source": "ai",
        "category": "Grammar",
        "severity": "general",
        "confidence": 80,
        # 样例取自 GoSpatial 报告中的真实英文问题；不使用 "following status" 措辞，
        # 因为该短语已在 origin/main 的误报规则库中被确认为正确用法（人审结论），
        # is_noise 会按规则库优先将其判为误报，与本测试要验证的 value_score 门槛无关。
        "original_text": "This sections describes the cleaning procedure.",
        "suggestion": "This section describes the cleaning procedure.",
        "description": "Grammar: singular/plural mismatch",
    }
    assert is_verifiable_ai_text_issue(issue) is True
    assert is_noise(issue) is False
    assert value_score(issue) >= 45, f"value_score={value_score(issue)} should pass threshold"


def test_audit_max_tokens_scales_with_content():
    """输出 token 上限应随内容长度自适应，且不低于默认 4096。"""
    from app.utils.ai_client import _audit_max_tokens
    base = _audit_max_tokens(0)
    assert base >= 4096
    large = _audit_max_tokens(12000)
    assert large > base
    assert large <= base * 2


def test_extract_json_marks_truncated():
    """截断且没有任何已闭合 issue 时，打 _degraded 并保持 issues 为空。"""
    broken = '{"issues": [{"category": "Grammar", "original_text": "abc", "suggestion": "abd", "confidence": 80'
    result = AIClient._extract_json(broken, {"issues": []})
    assert result.get("_degraded") is True
    assert result.get("_degraded_reason") == "json_truncated"
    assert result.get("issues") == []


def test_extract_json_salvages_closed_issues():
    """截断 JSON 应回收已经闭合的 issue，并标记 json_truncated_salvaged。"""
    broken = (
        '{"issues": ['
        '{"category": "Grammar", "original_text": "abc", "suggestion": "abd", "confidence": 80}, '
        '{"category": "Terminology", "original_text": "foo", "suggestion": "bar"'
    )
    result = AIClient._extract_json(broken, {"issues": []})
    assert result.get("_degraded") is True
    assert result.get("_degraded_reason") == "json_truncated_salvaged"
    assert len(result["issues"]) == 1
    assert result["issues"][0]["original_text"] == "abc"


def test_trademark_reading_order_artifact_filtered():
    """商标声明被 PDF 阅读顺序打乱时，AI 的商标归属问题属于解析伪影。"""
    assert pipeline.is_trademark_reading_order_artifact(
        "® are trademarks or registered trademarks of Microsoft Corporation.",
        "Microsoft® and Windows® are trademarks or registered trademarks of Microsoft Corporation.",
    ) is True
    # 文本层把 ™ 提取成字面量 TM 时同样属于阅读顺序伪影
    assert pipeline.is_trademark_reading_order_artifact(
        "TM is the trademark of Intel Corporation or its subsidiaries in the U.S. and/or other countries.",
        "Intel® and Intel Core™ are trademarks of Intel Corporation or its subsidiaries in the U.S. and/or other countries.",
    ) is True
    # 原文商标符号紧跟商标名时属于真实文本，不应误判
    assert pipeline.is_trademark_reading_order_artifact(
        "Microsoft® is a trademark of Microsoft Corporation.",
        "Microsoft® is a registered trademark of Microsoft Corporation.",
    ) is False


def test_broken_word_extraction_artifact_filtered():
    """PDF 表格按字符间距断词产生的碎片文本不应作为拼写问题上报。"""
    assert pipeline.is_broken_word_extraction_artifact("Powe rswi tcha n d") is True
    # 正常英文短语里的短词不应误判
    assert pipeline.is_broken_word_extraction_artifact("Turn off the tap now") is False
    assert pipeline.is_broken_word_extraction_artifact("Power switch and") is False
    assert pipeline.is_broken_word_extraction_artifact("air gap set up a b") is False
    assert pipeline.is_broken_word_extraction_artifact("set up a p a c k") is False
    assert pipeline.is_broken_word_extraction_artifact("data a vailable") is False
    assert pipeline.is_broken_word_extraction_artifact("a b c d e") is False


def test_extraction_artifact_ai_issue_is_noise():
    broken_word_issue = {
        "source": "ai",
        "rule": "Spelling/word-break integrity in table content",
        "category": "术语一致性",
        "severity": "general",
        "original_text": "Powe rswi tcha n d",
        "context": "POWE Rswi tcha n d",
        "suggestion": "Power switch and",
        "description": "",
        "confidence": 70,
    }
    assert pipeline.is_noise(broken_word_issue) is True
    assert select_review_issues([broken_word_issue]) == []


def test_symbol_legend_stray_fragment_ai_issue_is_noise():
    issue = {
        "source": "ai",
        "rule": "AI",
        "category": "可读性",
        "severity": "general",
        "original_text": "T10AH250V Fuse specification Indicates the fuse specification to be followed.",
        "context": "Symbol Title Description T10AH250V Fuse specification Indicates the fuse specification to be followed.",
        "suggestion": "Remove the stray fragment before Fuse specification.",
        "description": "Truncated fragment preceding the symbol legend definition.",
        "confidence": 80,
    }
    assert pipeline.is_symbol_legend_extraction_noise(
        issue["original_text"], issue["suggestion"], issue["description"]
    ) is True
    assert pipeline.is_noise(issue) is True
    assert select_review_issues([issue]) == []


def test_legal_disclaimer_rewrite_ai_issue_is_noise():
    issue = {
        "source": "ai",
        "rule": "AI",
        "category": "表述不准确",
        "severity": "suggestion",
        "original_text": "MGI shall not be liable for any loss arising from the use of this product.",
        "context": "To the maximum extent permitted by law, MGI shall not be liable for any loss arising from the use of this product.",
        "suggestion": "MGI is not responsible for damages that may occur when customers use the product.",
        "description": "Rewrite the legal disclaimer for clarity.",
        "confidence": 80,
    }
    assert pipeline.is_legal_disclaimer_rewrite_noise(issue["original_text"], issue["suggestion"]) is True
    assert pipeline.is_noise(issue) is True
    assert select_review_issues([issue]) == []


def test_figure_illustration_word_order_ai_issue_is_noise():
    issue = {
        "source": "ai",
        "rule": "AI",
        "category": "可读性",
        "severity": "suggestion",
        "original_text": "Figures in this manual are all illustrations.",
        "context": "Figures in this manual are all illustrations.",
        "suggestion": "All figures in this manual are illustrations.",
        "description": "Word order can be improved.",
        "confidence": 75,
    }
    assert pipeline.is_figure_illustration_word_order_noise(issue["original_text"], issue["suggestion"]) is True
    assert pipeline.is_noise(issue) is True
    assert select_review_issues([issue]) == []


def test_latin_cjk_boundary_space_suggestion_is_noise():
    # 数字/英文与中文之间的排版空格是中英混排常见风格，不是「中文文字间多余空格」
    assert pipeline.is_cjk_latin_boundary_space_style("第105 页", "第105页") is True
    assert pipeline.is_cjk_latin_boundary_space_style("V5.4 及以上", "V5.4及以上") is True
    assert pipeline.is_cjk_latin_boundary_space_style("AMR 序列", "AMR序列") is True
    # 反向（补空格）同样是风格问题，收敛到一致性规则，不在单点上报
    assert pipeline.is_cjk_latin_boundary_space_style("设置Barcode", "设置 Barcode") is True
    assert pipeline.is_cjk_latin_boundary_space_style("大于500 MB", "大于 500 MB") is True
    # 中文与中文之间的词内空格是真实问题，保留
    assert pipeline.is_cjk_latin_boundary_space_style("满 足要求", "满足要求") is False
    # 英文断词、数字与单位缺空格（非中文-非中文）是真实问题，保留
    assert pipeline.is_cjk_latin_boundary_space_style("High-throu ghput", "High-throughput") is False
    assert pipeline.is_cjk_latin_boundary_space_style("5mL", "5 mL") is False

    issue = {
        "source": "ai",
        "rule": "中文文字间不能有多余空格",
        "category": "术语一致性",
        "severity": "general",
        "original_text": "第105 页",
        "context": "参考第105 页“表格导入”步骤3。",
        "suggestion": "第105页",
        "description": "",
        "confidence": 90,
    }
    assert pipeline.is_noise(issue) is True
    assert select_review_issues([issue]) == []

    add_space_issue = {
        "source": "ai",
        "rule": "中英文之间应保留空格",
        "category": "术语一致性",
        "severity": "general",
        "original_text": "执行如下步骤设置Barcode",
        "context": "执行如下步骤设置Barcode。",
        "suggestion": "执行如下步骤设置 Barcode",
        "description": "",
        "confidence": 80,
    }
    assert pipeline.is_noise(add_space_issue) is True
    assert select_review_issues([add_space_issue]) == []


def test_ui_object_insertion_without_evidence_is_noise():
    # 原文图标字形未进入文本层，AI 报「图标缺失」，唯一改动只是插入「对应图标」
    assert pipeline.is_ui_object_insertion_without_evidence(
        "点击 找到为该分析流程创建的所有规则。",
        "点击对应图标找到为该分析流程创建的所有规则。",
    ) is True
    assert pipeline.is_ui_object_insertion_without_evidence(
        "如需删除已录入的样本信息，在待删除样本信息所在记录行，点击 。",
        "如需删除已录入的样本信息，在待删除样本信息所在记录行，点击对应图标。",
    ) is True
    # AI 凭空补一个【查询】之类的按钮名，同样是无证据上报
    assert pipeline.is_ui_object_insertion_without_evidence(
        "点击 定位到目标批次。",
        "点击【查询】定位到目标批次。",
    ) is True
    assert pipeline.is_ui_object_insertion_without_evidence(
        "点击顶部右侧 ，进入消息中心",
        "点击顶部右侧【消息】图标，进入消息中心",
    ) is True
    # 原文已出现图标名、或并非仅插入 UI 对象名词时，不判为无证据
    assert pipeline.is_ui_object_insertion_without_evidence(
        "点击【保存】按钮。",
        "点击【保存】。",
    ) is False

    issue = {
        "source": "ai",
        "rule": "图标缺失导致操作对象不明确",
        "category": "格式排版",
        "severity": "general",
        "original_text": "点击 ，定位到待查看分析任务所在记录行",
        "context": "点击 ，定位到待查看分析任务所在记录行",
        "suggestion": "点击对应图标，定位到待查看分析任务所在记录行",
        "description": "",
        "confidence": 70,
    }
    assert pipeline.is_noise(issue) is True
    assert select_review_issues([issue]) == []


def test_broken_glyph_extraction_ai_issue_is_noise():
    # PDF 符号字体的项目符号/图标字形在文本层被解析成 U+FFFD，AI 据此误报格式问题
    issue = {
        "source": "ai",
        "rule": "项目符号应为标准无序列表符号",
        "category": "格式排版",
        "severity": "suggestion",
        "original_text": "\ufffd如需录入多个样本信息",
        "context": "\ufffd如需录入多个样本信息",
        "suggestion": "将项目符号统一为标准无序列表符号",
        "description": "",
        "confidence": 80,
    }
    assert pipeline.is_broken_glyph_extraction_artifact(issue["original_text"]) is True
    assert pipeline.is_noise(issue) is True
    assert select_review_issues([issue]) == []


_TOC_CONTENT = "\n".join([
    "Contents",
    "Safety 1",
    "Device overview 2",
    "Device 3",
    "Specifications 4",
    "Troubleshooting 5",
    "Maintaining the device 6",
    "Daily maintenance 6",
    "Cleaning the device 7",
    "Storage and transportation 8",
    "",
    "01",
    "This chapter describes safety information.",
    "",
    "Figure 9 Loading interface",
    "",
    "Some figure body line here.",
    "",
])


def test_extract_chapter_prefers_toc_heading_over_figure_caption():
    content = _TOC_CONTENT + "\n".join([
        "Troubleshooting",
        "",
        "If malfunction occurs, follow the prompt.",
        "",
        "the the",
    ])
    position = content.index("the the")
    assert review_api.extract_chapter(content, position) == "Troubleshooting"


def test_extract_chapter_recognizes_optional_heading():
    content = _TOC_CONTENT + "\n".join([
        "(Optional) Powering off the device",
        "",
        "Turn the power switch to the position.",
    ])
    position = content.index("Turn the power switch")
    assert review_api.extract_chapter(content, position) == "(Optional) Powering off the device"


def test_extract_chapter_ignores_page_range_table_cell():
    content = _TOC_CONTENT + "\n".join([
        "Device",
        "",
        "1 to 36",
        "",
        "the the",
    ])
    position = content.index("the the")
    assert review_api.extract_chapter(content, position) == "Device"


def test_intervening_section_heading_ignores_operation_body_lines():
    body_lines = [
        "Insert the cartridge into slot A and close it",
        "Press the Open button to release the cover",
        "Please refer to the table below for insert size",
        "Remove the sealing film from the reagent plate",
        "Step 3 Load the flow cell and start the run",
    ]
    for line in body_lines:
        assert review_api._has_intervening_section_heading(line) is False

    assert review_api._has_intervening_section_heading("Safety Instructions") is True
    assert review_api._has_intervening_section_heading("WARNING") is True
    assert review_api._has_intervening_section_heading("警告") is True


def test_section_heading_regex_rejects_operation_sentences():
    """黑名单外动词开头的操作句一律不得判为标题（结构性判据，非枚举）。"""
    assert (
        review_api._line_looks_like_section_heading(
            "Install the reagent cartridge carefully", toc_titles=None
        )
        is False
    )
    assert (
        review_api._line_looks_like_section_heading(
            "Wipe the surface with a soft cloth", toc_titles=None
        )
        is False
    )
    assert (
        review_api._line_looks_like_section_heading(
            "Verify the connection to the power supply", toc_titles=None
        )
        is False
    )
    assert (
        review_api._line_looks_like_section_heading(
            "Load the sample into the tray", toc_titles=None
        )
        is False
    )
    assert (
        review_api._line_looks_like_section_heading(
            "Dilute the sample with buffer solution", toc_titles=None
        )
        is False
    )
    assert (
        review_api._line_looks_like_section_heading(
            "Record the lot number in the log", toc_titles=None
        )
        is False
    )
    assert (
        review_api._line_looks_like_section_heading(
            "Discard the waste according to regulations", toc_titles=None
        )
        is False
    )
    assert (
        review_api._line_looks_like_section_heading(
            "Transport the instrument upright only", toc_titles=None
        )
        is False
    )


def test_section_heading_regex_accepts_real_headings():
    real_headings = [
        "General Information",
        "Safety Precautions",
        "Product Specifications",
        "Installation",
        "Intended Use",
        "Ordering Information",
        "Troubleshooting",
    ]
    for line in real_headings:
        assert review_api._line_looks_like_section_heading(line, toc_titles=None) is True


def test_safety_label_survives_intervening_operation_sentence():
    """WARNING 与风险词之间夹一行操作正文时，安全标注不得被判为已跨章节。"""
    content = (
        "WARNING\n"
        "Keep the reagent away from open flames\n"
        "Install the reagent cartridge carefully\n"
        "Keep away from heat and ignition sources"
    )
    position = content.index("heat and ignition")

    assert review_api._hazard_has_enclosing_safety_label(content, position, None) is True
    assert review_api._hazard_has_enclosing_safety_label(content, position) is True


def test_section_heading_uses_toc_when_available():
    """传入含 TOC 的完整文档时，TOC 未列的行不得仅凭正则判为标题。"""
    toc = "\n".join(f"Section {index} Title {index}" for index in range(1, 10))
    content = toc + "\n" + "Install the reagent cartridge carefully"
    toc_titles = review_api._toc_heading_titles(content)

    assert "section 3 title" in toc_titles
    assert (
        review_api._line_looks_like_section_heading(
            "Install the reagent cartridge carefully", toc_titles=toc_titles
        )
        is False
    )
    assert (
        review_api._line_looks_like_section_heading("Section 3 Title", toc_titles=toc_titles)
        is True
    )
