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
    """截断 JSON 应打 _degraded 标记而非静默返回空。"""
    from app.utils.ai_client import AIClient
    broken = '{"issues": [{"category": "Grammar", "original_text": "abc", "suggestion": "abd", "confidence": 80'
    result = AIClient._extract_json(broken, {"issues": []})
    assert result.get("_degraded") is True
    assert result.get("_degraded_reason") == "json_truncated"


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
