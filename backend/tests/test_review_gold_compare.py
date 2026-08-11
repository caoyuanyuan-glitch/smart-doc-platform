from types import SimpleNamespace

from app.api.review import _assign_gold_issue_matches
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


def test_audit_trace_model_is_registered():
    assert "audit_traces" in Base.metadata.tables
