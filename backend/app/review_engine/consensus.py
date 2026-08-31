"""On-demand second-provider consensus for review AI."""

from __future__ import annotations

HIGH_RISK_CATEGORIES = {
    "安全",
    "安全警示",
    "引用完整性",
    "术语一致性",
    "数据准确性",
}
HIGH_RISK_SEVERITIES = {"fatal", "serious"}


def issue_confidence(issue) -> int:
    if isinstance(issue, dict):
        value = issue.get("confidence", 0)
    else:
        value = getattr(issue, "confidence", 0)
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def issue_field(issue, name: str, default: str = "") -> str:
    if isinstance(issue, dict):
        return str(issue.get(name, default) or default)
    return str(getattr(issue, name, default) or default)


def is_high_risk_issue(issue) -> bool:
    category = issue_field(issue, "category")
    severity = issue_field(issue, "severity").lower()
    return category in HIGH_RISK_CATEGORIES or severity in HIGH_RISK_SEVERITIES


def should_trigger_second_provider(
    issues,
    *,
    confidence_threshold: int = 70,
    rule_ai_conflict: bool = False,
    require_consensus: bool = False,
) -> tuple[bool, str]:
    if require_consensus:
        return True, "explicit_request"
    if rule_ai_conflict:
        return True, "rule_ai_conflict"
    for issue in issues or []:
        if is_high_risk_issue(issue) and issue_field(issue, "source").lower() == "ai":
            return True, "high_risk"
        if issue_field(issue, "source").lower() == "ai" and issue_confidence(issue) < confidence_threshold:
            return True, "low_confidence"
    return False, ""


def select_consensus_candidates(issues, *, confidence_threshold: int = 70) -> list:
    selected = []
    for issue in issues or []:
        if issue_field(issue, "source").lower() != "ai":
            continue
        if is_high_risk_issue(issue) or issue_confidence(issue) < confidence_threshold:
            selected.append(issue)
    return selected
