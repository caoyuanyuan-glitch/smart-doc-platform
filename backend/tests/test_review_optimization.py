from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pytest

from app.api import review as review_api
from app.review_engine.basis_trace import build_basis_trace
from app.review_engine.consensus import should_trigger_second_provider
from app.review_engine.paths import ReviewPathError, resolve_review_file_path
from app.review_engine.safe_zip import UnsafeZipError, safe_extract_zip
from app.review_engine.visual import map_visual_status
from app.rules.reference_integrity_rule import ReferenceIntegrityRule
from app.services.chunker import AuditResultMerger, CrossChapterConsistencyChecker, create_smart_chunker


def test_dashboard_quality_metrics_keep_false_positives_in_rate():
    issues = [
        SimpleNamespace(source="rule", status="false_positive", original_text="rule hit", suggestion="fix", audit_basis="规范", rule="R999"),
        SimpleNamespace(source="ai", status="pending", original_text="ai hit", suggestion="fix it", audit_basis="规范条款", rule="AI-001"),
        SimpleNamespace(source="manual", status="pending", original_text="manual hit", suggestion="fix", audit_basis="人工", rule="M-001"),
    ]
    metrics = review_api._dashboard_quality_metrics(issues)
    visible = review_api._dashboard_visible_issues(issues)
    assert metrics["false_positive_count"] == 1
    assert metrics["false_positive_rate"] == 0.5
    assert metrics["platform_reported"] == 2
    assert len(visible) == 2
    assert all(str(item.status) != "false_positive" for item in visible)


def test_normalize_providers_default_single_only():
    assert review_api._normalize_providers(providers="qwen,deepseek") == ["qwen"]


def test_chunker_short_document_and_offsets():
    chunker = create_smart_chunker(max_chunks=8, max_chars=80, overlap=10)
    chunks = chunker.chunk_document("Hello world")
    assert chunks
    assert chunks[0].start == 0
    assert chunks[0].end == len("Hello world")
    assert chunks[0].chunk_id


def test_chunker_chapter_boundary_and_overlap():
    text = "第1章 概述\n" + ("A" * 60) + "\n\n第2章 安装\n" + ("B" * 60)
    chunker = create_smart_chunker(max_chunks=8, max_chars=80, overlap=8)
    chunks = chunker.chunk_document(text)
    assert len(chunks) >= 2
    assert chunks[0].chapter.startswith("第1章")
    assert any("第2章" in item.chapter for item in chunks)


def test_chunker_long_paragraph_hard_split():
    text = "C" * 1200
    chunker = create_smart_chunker(max_chunks=6, max_chars=400, overlap=40)
    chunks = chunker.chunk_document(text)
    assert len(chunks) >= 3
    assert chunks[0].end > chunks[0].start


def test_chunker_mixed_language_and_consistency():
    text = "1 简介\nUse RNASeq Kit in chapter one.\n\n2 安装\nUse rnaseq Kit again."
    chunks = create_smart_chunker(max_chunks=8, max_chars=200).chunk_document(text)
    issues = CrossChapterConsistencyChecker().check(chunks)
    merged = AuditResultMerger().merge([issues, issues])
    assert merged
    assert len(merged) == len(issues)


def test_safe_extract_zip_rejects_path_traversal(tmp_path):
    zip_path = tmp_path / "bad.zip"
    with ZipFile(zip_path, "w") as handle:
        handle.writestr("../escape.txt", "nope")
    with pytest.raises(UnsafeZipError):
        safe_extract_zip(zip_path, tmp_path / "out")


def test_safe_extract_zip_rejects_member_limit(tmp_path):
    zip_path = tmp_path / "many.zip"
    with ZipFile(zip_path, "w") as handle:
        for index in range(6):
            handle.writestr(f"word/f{index}.xml", "x")
    with pytest.raises(UnsafeZipError):
        safe_extract_zip(zip_path, tmp_path / "out", max_members=3)


def test_safe_extract_zip_allows_docx_members(tmp_path):
    zip_path = tmp_path / "ok.zip"
    with ZipFile(zip_path, "w") as handle:
        handle.writestr("word/document.xml", "<w:document/>")
    extracted = safe_extract_zip(zip_path, tmp_path / "out", allowed_prefixes=("word/",))
    assert extracted
    assert Path(extracted[0]).exists()


def test_resolve_review_file_path_rejects_escape(tmp_path):
    escaped = resolve_review_file_path(tmp_path, "../secret.txt")
    assert escaped == (tmp_path / "secret.txt").resolve()
    assert escaped.parent == tmp_path.resolve()
    with pytest.raises(ReviewPathError):
        resolve_review_file_path(tmp_path, "..")
    target = tmp_path / "doc.docx"
    target.write_text("ok", encoding="utf-8")
    assert resolve_review_file_path(tmp_path, "doc.docx") == target.resolve()


def test_cache_key_changes_with_prompt_and_provider(monkeypatch):
    document = SimpleNamespace(id=1, filename="a.docx", file_type="docx", file_size=1, content="x")
    monkeypatch.setattr(review_api, "_review_cache_version", lambda: "v1")
    monkeypatch.setattr(review_api, "_ai_provider_cache_fingerprint", lambda: "p1")
    key1 = review_api._build_review_cache_key(document, "hybrid")
    monkeypatch.setattr(review_api, "REVIEW_PROMPT_VERSION", "review-prompt-v9")
    from app.review_engine import versions
    monkeypatch.setattr(versions, "PROMPT_VERSION", "review-prompt-v9")
    key2 = review_api._build_review_cache_key(document, "hybrid")
    assert key1 != key2


def test_consensus_triggers_on_low_confidence_only():
    high = [{"source": "ai", "confidence": 90, "category": "标点", "severity": "general"}]
    low = [{"source": "ai", "confidence": 40, "category": "标点", "severity": "general"}]
    assert should_trigger_second_provider(high) == (False, "")
    triggered, reason = should_trigger_second_provider(low)
    assert triggered is True
    assert reason == "low_confidence"


def test_visual_status_mapping():
    assert map_visual_status("confirm") == "verified"
    assert map_visual_status("reject") == "rejected"
    assert map_visual_status("skipped", "kimi_unavailable") == "provider_unavailable"
    assert map_visual_status("error") == "failed"


def test_basis_trace_sources():
    none_trace = build_basis_trace(sections=None)
    assert none_trace["basis_source"] == "none"
    es_trace = build_basis_trace(sections=[{"label": "指南", "text": "x"}], es_available=True, es_hit=True)
    assert es_trace["basis_source"] == "es"
    fallback = build_basis_trace(sections=[{"label": "本地", "text": "y"}], fallback=True, fallback_reason="es_unavailable")
    assert fallback["basis_source"] == "local_fallback"


def test_chinese_and_english_reference_integrity():
    rule = ReferenceIntegrityRule()
    text = "请参见表 3。\n\n图 2 显示结果。\nSee Table 9 and Figure 8.\n"
    issues = rule.check(text)
    originals = {item["original_text"] for item in issues}
    assert "表3" in originals or "表 3" in originals or any("表" in item for item in originals)
    assert any("Figure" in item or "Table" in item for item in originals)


def test_review_engine_exports_are_real():
    from app.review_engine import AICandidateEngine, ReportAggregator, ReviewOrchestrator
    assert ReviewOrchestrator is not None
    result = ReviewOrchestrator().run([])
    assert result.issues == []
    assert AICandidateEngine().collect([]) == []
    assert ReportAggregator().aggregate([1]) == [1]


def test_visual_all_providers_unavailable(monkeypatch):
    monkeypatch.setenv("REVIEW_VISUAL_PROVIDERS", "kimi,qwen")
    monkeypatch.setattr(review_api, "_visual_provider_available", lambda name: False)
    result = review_api._verify_review_issue_visually(b"png", {"original_text": "x"}, 1, 7)
    assert result["visual_status"] == "provider_unavailable"
    assert result["attempts"]


def test_visual_kimi_confirm_does_not_count_as_skipped(monkeypatch):
    monkeypatch.setenv("REVIEW_VISUAL_PROVIDERS", "kimi,qwen")
    monkeypatch.setattr(review_api, "_visual_provider_available", lambda name: True)
    monkeypatch.setattr(
        review_api.ai_client,
        "verify_review_issue_from_image",
        lambda *args, **kwargs: {"decision": "confirm", "reason": "visible"},
    )
    result = review_api._verify_review_issue_visually(b"png", {"original_text": "x"}, 1, 7)
    assert result["visual_status"] == "verified"
    assert result["provider"] == "kimi"


def test_persist_progress_and_reclaim_stale_running():
    from datetime import datetime, timedelta

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.crud.review import persist_review_progress, reclaim_stale_running_reviews
    from app.database import Base
    from app.models.document import Document
    from app.models.review import Review

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    document = Document(filename="manual.docx", file_type="docx", content="body")
    db.add(document)
    db.commit()
    review = Review(document_id=document.id, mode="hybrid", status="running")
    db.add(review)
    db.commit()

    persist_review_progress(db, review.id, "running", "AI智能审核", 40, "working")
    db.refresh(review)
    assert review.stage == "AI智能审核"
    assert review.progress == 40
    assert review.heartbeat_at is not None

    review.heartbeat_at = datetime.utcnow() - timedelta(seconds=2000)
    db.commit()
    reclaimed = reclaim_stale_running_reviews(db, timeout_seconds=30)
    db.refresh(review)
    assert reclaimed == 1
    assert review.status == "failed"
