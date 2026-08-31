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
