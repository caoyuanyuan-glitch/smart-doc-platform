from app.review_engine.dashboard_metrics import compute_quality_rates


def test_detection_rate_unset_without_manual_supplements():
    result = compute_quality_rates(
        platform_detected=12,
        manual_supplemented=0,
        false_positive_count=3,
        platform_reported=15,
    )

    assert result["detection_rate"] is None
    assert result["detection_rate_available"] is False
    assert result["false_positive_rate"] == 0.2


def test_detection_rate_uses_manual_supplements_as_misses():
    result = compute_quality_rates(
        platform_detected=8,
        manual_supplemented=2,
        false_positive_count=1,
        platform_reported=9,
    )

    assert result["detection_rate_available"] is True
    assert result["detection_rate"] == 0.8
    assert result["expected_issues"] == 10


def test_false_positive_rate_uses_unfiltered_platform_set():
    from types import SimpleNamespace
    from app.api import review as review_api

    issues = [
        SimpleNamespace(source="rule", status="false_positive", original_text="rule hit", suggestion="fix", audit_basis="规范", rule="R999"),
        SimpleNamespace(source="ai", status="confirmed", original_text="ai hit", suggestion="fix it", audit_basis="规范条款", rule="AI-001"),
    ]
    metrics = review_api._dashboard_quality_metrics(issues)
    visible = review_api._dashboard_visible_issues(issues)
    assert metrics["false_positive_count"] == 1
    assert metrics["false_positive_rate"] == 0.5
    assert [item.status for item in visible] == ["confirmed"]
