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
