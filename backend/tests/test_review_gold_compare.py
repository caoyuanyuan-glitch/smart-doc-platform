from types import SimpleNamespace
from unittest.mock import patch

from app.api.review import _assign_gold_issue_matches, _gold_issue_match_detail, _parse_gold_serial
from app.api.auth import _resolve_secret_key
from app.database import Base

import app.models.audit_trace  # noqa: F401


def _issue(issue_id, original_text, category="术语", rule="TERM-001"):
    return SimpleNamespace(
        id=issue_id,
        category=category,
        rule=rule,
        type=category,
        severity="general",
        chapter="章节1",
        original_text=original_text,
        suggestion="修正",
        description="说明",
    )


def test_gold_compare_matches_each_issue_only_once():
    gold_rows = [
        {"index": 1, "wrong_text": "Buffer A", "issue_type": "术语"},
    ]
    issues = [
        _issue(11, "Buffer A"),
        _issue(12, "Buffer A"),
    ]

    matched_pairs, matched_gold, matched_issue = _assign_gold_issue_matches(gold_rows, issues)

    assert len(matched_pairs) == 1
    assert matched_gold == {0}
    assert len(matched_issue) == 1


def test_gold_compare_prefers_global_one_to_one_assignment():
    gold_rows = [
        {"index": 1, "wrong_text": "Buffer A", "issue_type": "术语"},
        {"index": 2, "wrong_text": "Buffer B", "issue_type": "术语"},
    ]
    issues = [
        _issue(21, "Buffer A"),
        _issue(22, "Buffer B"),
    ]

    matched_pairs, matched_gold, matched_issue = _assign_gold_issue_matches(gold_rows, issues)

    assert len(matched_pairs) == 2
    assert matched_gold == {0, 1}
    assert matched_issue == {0, 1}


def test_gold_compare_uses_global_optimal_matching_for_conflicts():
    gold_rows = [
        {"index": 1, "wrong_text": "Buffer A", "issue_type": "术语", "location": "章节1"},
        {"index": 2, "wrong_text": "Buffer A", "issue_type": "术语", "location": "章节2"},
    ]
    issues = [
        _issue(31, "Buffer A", category="术语", rule="TERM-001"),
        _issue(32, "Buffer A", category="术语", rule="TERM-001"),
    ]
    issues[0].chapter = "章节2"
    issues[1].chapter = "章节1"

    matched_pairs, matched_gold, matched_issue = _assign_gold_issue_matches(gold_rows, issues)

    assert len(matched_pairs) == 2
    assert matched_gold == {0, 1}
    assert matched_issue == {0, 1}
    assert matched_pairs[0]["issue_idx"] == 1
    assert matched_pairs[1]["issue_idx"] == 0


def test_gold_compare_large_issue_sets_keep_optimal_assignment():
    gold_rows = [{"index": i + 1, "wrong_text": f"Item {i + 1}", "issue_type": "术语"} for i in range(17)]
    issues = [_issue(100 + i, f"Item {i + 1}") for i in range(17)]

    custom_scores = {
        (0, 0): 95,
        (0, 1): 94,
        (1, 0): 93,
        (1, 1): 0,
    }

    def fake_match_detail(row, issue):
        gold_idx = int(row["index"]) - 1
        issue_idx = issue.id - 100
        score = custom_scores.get((gold_idx, issue_idx), 0)
        return {
            "score": score,
            "reason": f"score_{score}",
            "location_match": False,
            "location_reason": "mock",
        }

    with patch("app.api.review._gold_issue_match_detail", side_effect=fake_match_detail):
        matched_pairs, matched_gold, matched_issue = _assign_gold_issue_matches(gold_rows, issues)

    assert len(matched_pairs) == 2
    assert matched_gold == {0, 1}
    assert matched_issue == {0, 1}
    assert {(item["gold_idx"], item["issue_idx"]) for item in matched_pairs} == {(0, 1), (1, 0)}


def test_gold_compare_location_affects_score():
    gold_row = {"index": 1, "wrong_text": "Buffer A", "issue_type": "术语", "location": "章节1"}
    exact_issue = _issue(41, "Buffer A")
    wrong_issue = _issue(42, "Buffer A")
    wrong_issue.chapter = "章节9"

    exact_detail = _gold_issue_match_detail(gold_row, exact_issue)
    wrong_detail = _gold_issue_match_detail(gold_row, wrong_issue)

    assert exact_detail["score"] > wrong_detail["score"]
    assert exact_detail["location_match"] is True
    assert wrong_detail["location_match"] is False


def test_parse_gold_serial_accepts_int_float_and_string():
    assert _parse_gold_serial(1) == 1
    assert _parse_gold_serial(1.0) == 1
    assert _parse_gold_serial(" 1 ") == 1
    assert _parse_gold_serial("abc") is None


def test_resolve_secret_key_rejects_default_in_production():
    try:
        _resolve_secret_key("", environment="production")
    except RuntimeError as exc:
        assert "JWT_SECRET_KEY" in str(exc)
    else:
        raise AssertionError("expected RuntimeError for missing production JWT secret")


def test_resolve_secret_key_requires_long_secret_in_production():
    try:
        _resolve_secret_key("short-secret", environment="production")
    except RuntimeError as exc:
        assert "32" in str(exc)
    else:
        raise AssertionError("expected RuntimeError for short production JWT secret")


def test_audit_trace_model_is_registered():
    assert "audit_traces" in Base.metadata.tables
