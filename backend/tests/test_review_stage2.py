import json
import inspect
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import review as review_api
from app.crud.review import create_review, get_issues, get_review
from app.database import Base
from app.models.document import Document
from app.models.issue import Issue  # noqa: F401
from app.models.review import Review  # noqa: F401
from app.models.user import User
from app.review_engine.language_segments import segment_text_by_language
from app.review_engine.staged_pipeline import (
    adjudicate_and_deduplicate,
    extract_protected_literals,
    resolve_pipeline_mode,
    run_staged_snippet_pipeline,
    select_deterministic,
    select_high_risk_spans,
    validate_ai_evidence,
)
from app.schemas.review import ReviewCreate


def test_rule_and_ai_same_span_are_merged():
    rules = [{
        "rule": "SPELL-001",
        "source": "rule",
        "original_text": "accomodate",
        "suggestion": "accommodate",
        "description": "Dictionary match",
        "audit_basis": "spelling",
        "start": 10,
        "end": 20,
        "position": "10-20",
        "status": "confirmed",
    }]
    ai_results = [{
        "rule": "AI",
        "source": "ai",
        "original_text": "accomodate",
        "suggestion": "accommodate",
        "evidence": "Dictionary match",
        "start": 10,
        "end": 20,
        "source_start": 10,
        "source_end": 20,
        "status": "confirmed",
    }]
    text = "Please accomodate the sample."
    issues, _diag = run_staged_snippet_pipeline(text, rules, ai_results=ai_results)
    assert len(issues) == 1
    assert issues[0]["source"] == "rule+ai"
    assert issues[0]["status"] == "confirmed"


def test_different_units_are_not_merged():
    rules = [
        {
            "rule": "UNIT-001",
            "source": "rule",
            "original_text": "5μL",
            "suggestion": "5 μL",
            "description": "unit space",
            "start": 0,
            "end": 3,
            "position": "0-3",
        },
        {
            "rule": "UNIT-001",
            "source": "rule",
            "original_text": "3000rpm",
            "suggestion": "3000 rpm",
            "description": "unit space",
            "start": 10,
            "end": 17,
            "position": "10-17",
        },
    ]
    merged = adjudicate_and_deduplicate(select_deterministic(rules), [])
    originals = {item["original_text"] for item in merged}
    assert originals == {"5μL", "3000rpm"}


def test_protected_literals_are_not_modified():
    text = "Load 10 μL DNBSEQ reagent."
    protected = extract_protected_literals(text)
    assert any("DNBSEQ" in item for item in protected)
    validated = validate_ai_evidence(
        [{
            "original_text": "Load 10 μL DNBSEQ reagent.",
            "suggestion": "Load 10 μL sequencer reagent.",
            "evidence": "Prefer generic name",
            "source_start": 0,
            "source_end": len(text),
            "status": "confirmed",
        }],
        text,
        protected_literals=protected,
    )
    assert validated[0]["status"] == "pending"
    assert validated[0].get("rejected_reason") == "protected_literal"


def test_ai_without_evidence_is_pending():
    validated = validate_ai_evidence(
        [{
            "original_text": "should recording",
            "suggestion": "should record",
            "source_start": 0,
            "source_end": 16,
            "status": "confirmed",
        }],
        "should recording the sample ID.",
    )
    assert validated[0]["status"] == "pending"


def test_ai_source_span_must_match_original_text():
    validated = validate_ai_evidence(
        [{
            "original_text": "not-in-source",
            "suggestion": "in source",
            "evidence": "model claimed an error",
            "source_start": 0,
            "source_end": 3,
            "status": "confirmed",
        }],
        "Please record the sample ID.",
    )
    assert validated[0]["status"] == "pending"
    assert validated[0]["location_quality"] == "unavailable"


def test_rule_zero_hit_high_risk_span_is_selected():
    text = "Do not start the run before the reagent is loaded.\nPlease record the sample ID."
    segments = segment_text_by_language(text)
    spans = select_high_risk_spans(segments, [], text)
    assert spans
    assert any("Do not start" in item["original_text"] for item in spans)
    _issues, diag = run_staged_snippet_pipeline(text, [])
    assert diag["high_risk_span_count"] >= 1
    assert diag["ai_window_count"] >= 1


def test_deterministic_rule_does_not_call_ai():
    text = "Please accomodate the tube."
    rules = [{
        "rule": "SPELL-001",
        "source": "rule",
        "original_text": "accomodate",
        "suggestion": "accommodate",
        "description": "Dictionary match",
        "audit_basis": "spelling dictionary",
    }]
    _issues, diag = run_staged_snippet_pipeline(text, rules)
    assert diag["confirmed_rule_count"] == 1
    assert diag["ai_window_count"] == 0
    assert diag["deterministic_skipped_ai"] is True


def test_ai_unavailable_keeps_rule_results():
    text = "融化后，使用涡漩振荡器振荡混匀。"
    rules = [{
        "rule": "CYY-CN-SPELL-009",
        "source": "rule",
        "original_text": "涡漩",
        "suggestion": "涡旋",
        "description": "错别字",
        "audit_basis": "词典命中",
    }]
    issues, diag = run_staged_snippet_pipeline(text, rules, ai_unavailable=True)
    assert diag["ai_unavailable"] is True
    assert any(item["original_text"] == "涡漩" for item in issues)
    assert issues[0]["status"] == "confirmed"


def test_summary_count_equals_final_issue_count():
    text = "融化后使用涡漩振荡器。Please accomodate the tube."
    rules = [
        {
            "rule": "CYY-CN-SPELL-009",
            "source": "rule",
            "original_text": "涡漩",
            "suggestion": "涡旋",
            "description": "错别字",
            "audit_basis": "词典",
        },
        {
            "rule": "SPELL-001",
            "source": "rule",
            "original_text": "accomodate",
            "suggestion": "accommodate",
            "description": "spelling",
            "audit_basis": "dictionary",
        },
    ]
    issues, diag = run_staged_snippet_pipeline(text, rules, ai_unavailable=True)
    assert diag["final_issue_count"] == len(issues)
    assert diag["confirmed_count"] + diag["pending_count"] + diag["ignored_count"] + diag["blocked_count"] == len(issues)


def test_same_issue_multiple_positions_are_preserved_in_staged():
    text = "使用涡漩振荡器。再次使用涡漩振荡器。"
    first = text.find("涡漩")
    second = text.find("涡漩", first + 1)
    rules = [
        {
            "rule": "CYY-CN-SPELL-009",
            "source": "rule",
            "original_text": "涡漩",
            "suggestion": "涡旋",
            "description": "错别字",
            "audit_basis": "词典",
            "start": first,
            "end": first + 2,
            "position": f"{first}-{first + 2}",
        },
        {
            "rule": "CYY-CN-SPELL-009",
            "source": "rule",
            "original_text": "涡漩",
            "suggestion": "涡旋",
            "description": "错别字",
            "audit_basis": "词典",
            "start": second,
            "end": second + 2,
            "position": f"{second}-{second + 2}",
        },
    ]
    issues, _diag = run_staged_snippet_pipeline(text, rules, ai_unavailable=True)
    assert len(issues) == 2


def test_resolve_pipeline_mode_snippet_defaults_to_staged(monkeypatch):
    monkeypatch.delenv("REVIEW_PIPELINE_MODE", raising=False)
    assert resolve_pipeline_mode(True) == "staged"
    assert resolve_pipeline_mode(False) == "legacy"
    monkeypatch.setenv("REVIEW_PIPELINE_MODE", "legacy")
    assert resolve_pipeline_mode(True) == "legacy"


def test_snippet_background_uses_staged_and_keeps_rules_without_ai(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr("app.database.SessionLocal", SessionLocal)
    monkeypatch.setattr(review_api, "ai_client", SimpleNamespace(
        has_any_client=False,
        summarize_usage_events=lambda **kwargs: {},
        get_usage_events=lambda **kwargs: [],
    ))
    monkeypatch.setattr(review_api, "get_rules", lambda db: [])
    monkeypatch.setattr(review_api, "get_terms", lambda db: [])
    monkeypatch.setattr(review_api, "get_knowledge_basis", lambda db: [])
    monkeypatch.setattr(review_api, "_load_review_spec_texts", lambda db: {
        "cn_style": "", "en_style": "", "common_errors": "", "final_checklists": "",
    })
    monkeypatch.setattr(review_api, "_load_false_positive_signatures_for_document", lambda db, document_id: set())
    monkeypatch.setattr(review_api, "set_progress", lambda *args, **kwargs: None)

    db = SessionLocal()
    try:
        db.add(User(id=1, username="tester", password_hash="x", role="admin", status="active"))
        text = "融化后，使用涡漩振荡器振荡混匀 5 s。"
        db.add(Document(id=1, filename="文本片段_demo.txt", file_type="txt", content=text, user_id=1, status="ready"))
        db.commit()
        review = create_review(db, ReviewCreate(document_id=1, mode="snippet:hybrid"))
        review_id = review.id
    finally:
        db.close()

    review_api._run_review_background(review_id, 1, "snippet:hybrid")

    db = SessionLocal()
    try:
        loaded = get_review(db, review_id)
        issues = get_issues(db, review_id)
        summary = json.loads(loaded.summary or "{}")
        assert loaded.status == "completed"
        assert summary.get("pipeline_mode") == "staged"
        assert summary.get("total") == len(issues)
        assert summary.get("degraded") is True
        assert summary.get("rule_completed") is True
        assert any("涡漩" in str(item.original_text or "") for item in issues)
    finally:
        db.close()
        engine.dispose()


def test_snippet_route_still_registered_for_staged_entry():
    paths = [getattr(route, "path", "") for route in review_api.router.routes]
    assert "/snippet" in paths
    source = inspect.getsource(review_api._run_review_background)
    assert "run_staged_snippet_pipeline" in source
    assert "_run_staged_ai_windows" in source
