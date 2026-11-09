"""Normalize issues.rule so it only stores real rule numbers."""
from __future__ import annotations

import re

RULE_NO_RE = re.compile(r"^[A-Z][A-Z0-9_-]*\d+$|^[A-Z]+(?:-[A-Z0-9]+)+$")

RULE_REWRITES = {
    "TERM": "TERM-INCONSIST",
    "TERM-CONSISTENCY-DB": "TERM-INCONSIST",
}
NON_RULE_CODES = {
    "COMPARE-PARAM": "compare_param",
    "COMPARE-FLOW": "compare_flow",
    "MANUAL-SUPPLEMENT": "manual_supplement",
}


def looks_like_rule_no(value: str) -> bool:
    text = str(value or "").strip()
    return bool(text) and bool(RULE_NO_RE.match(text))


def canonicalize_issue_rule(issue: dict) -> dict:
    """Keep issues.rule as a rule-table number. Move polluted values to source/check_type."""
    rule = str(issue.get("rule") or "").strip()
    upper = rule.upper()
    if upper in RULE_REWRITES:
        issue["rule"] = RULE_REWRITES[upper]
        return issue
    if upper in NON_RULE_CODES:
        check_type = NON_RULE_CODES[upper]
        issue["rule"] = ""
        issue["check_type"] = check_type
        if not issue.get("source") or issue.get("source") == "rule":
            issue["source"] = check_type
        return issue
    if rule and not looks_like_rule_no(rule):
        issue["check_type"] = "unmapped_rule_text"
        if not str(issue.get("description") or "").strip():
            issue["description"] = rule
        issue["rule"] = ""
        return issue
    return issue
