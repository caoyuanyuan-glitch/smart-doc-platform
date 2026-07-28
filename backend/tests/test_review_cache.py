import json
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
