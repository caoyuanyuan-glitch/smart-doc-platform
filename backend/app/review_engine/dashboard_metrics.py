"""Quality-rate helpers for the review statistics dashboard."""

from __future__ import annotations


def _ratio(count: int, total: int) -> float:
    return round(count / total, 4) if total else 0.0


def compute_quality_rates(
    *,
    platform_detected: int,
    manual_supplemented: int,
    false_positive_count: int,
    platform_reported: int,
) -> dict:
    """Build dashboard quality metrics.

    Detection rate is recall against human-supplemented misses.
    Without any manual supplements, recall is unknown and must stay unset.
    """
    expected = platform_detected + manual_supplemented
    detection_available = manual_supplemented > 0
    return {
        "platform_detected": platform_detected,
        "manual_supplemented": manual_supplemented,
        "expected_issues": expected,
        "false_positive_count": false_positive_count,
        "platform_reported": platform_reported,
        "accuracy_rate": _ratio(platform_detected, platform_reported),
        "false_positive_rate": _ratio(false_positive_count, platform_reported),
        "detection_rate": _ratio(platform_detected, expected) if detection_available else None,
        "detection_rate_available": detection_available,
    }
