"""Unified review issue statuses and report counts."""

from __future__ import annotations


STATUSES = {
    "detected",
    "pending",
    "confirmed",
    "false_positive",
    "ignored",
    "blocked",
}


def normalize_status(value: str) -> str:
    status = str(value or "").strip().lower()
    if status in STATUSES:
        return status
    if status in {"needs_review"}:
        return "blocked"
    if not status:
        return "detected"
    return "pending"


def compute_status_counts(issues) -> dict:
    counts = {
        "system_detected_count": 0,
        "pending_count": 0,
        "confirmed_count": 0,
        "false_positive_count": 0,
        "ignored_count": 0,
        "blocked_count": 0,
        "visual_unverified_count": 0,
        "reference_blocked_count": 0,
        "confirmed_fatal": 0,
        "confirmed_serious": 0,
        "confirmed_general": 0,
    }
    for issue in issues or []:
        if isinstance(issue, dict):
            status = normalize_status(issue.get("status"))
            severity = str(issue.get("severity") or "").lower()
            visual = issue.get("visual_verification") or {}
            if isinstance(visual, dict):
                visual_status = str(visual.get("status") or visual.get("visual_status") or "")
            else:
                visual_status = ""
            target_status = str(issue.get("target_status") or "")
        else:
            status = normalize_status(getattr(issue, "status", ""))
            severity = str(getattr(issue, "severity", "") or "").lower()
            visual_status = ""
            target_status = ""
        counts["system_detected_count"] += 1
        counts[f"{status}_count"] = counts.get(f"{status}_count", 0) + 1
        if status == "confirmed":
            if severity == "fatal":
                counts["confirmed_fatal"] += 1
            elif severity == "serious":
                counts["confirmed_serious"] += 1
            else:
                counts["confirmed_general"] += 1
        if visual_status and visual_status not in {"verified", "not_required"}:
            counts["visual_unverified_count"] += 1
        if target_status in {"target_not_parsed", "target_visual_only", "target_ambiguous"} or status == "blocked":
            if "引用" in str(getattr(issue, "category", "") if not isinstance(issue, dict) else issue.get("category") or ""):
                counts["reference_blocked_count"] += 1
    return counts
