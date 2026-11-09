from app.review_engine.issue_rule import canonicalize_issue_rule, looks_like_rule_no


def test_canonicalize_rewrites_term_aliases():
    issue = canonicalize_issue_rule({"rule": "TERM"})
    assert issue["rule"] == "TERM-INCONSIST"
    issue = canonicalize_issue_rule({"rule": "TERM-CONSISTENCY-DB"})
    assert issue["rule"] == "TERM-INCONSIST"


def test_canonicalize_splits_non_rule_codes():
    issue = canonicalize_issue_rule({"rule": "COMPARE-PARAM", "source": "rule"})
    assert issue["rule"] == ""
    assert issue["check_type"] == "compare_param"
    assert issue["source"] == "compare_param"
    issue = canonicalize_issue_rule({"rule": "MANUAL-SUPPLEMENT", "source": "manual"})
    assert issue["rule"] == ""
    assert issue["check_type"] == "manual_supplement"


def test_canonicalize_clears_chinese_rule_text():
    issue = canonicalize_issue_rule({"rule": "规则审核", "description": ""})
    assert issue["rule"] == ""
    assert issue["check_type"] == "unmapped_rule_text"
    assert issue["description"] == "规则审核"
    assert looks_like_rule_no("EXT-R005") is True
    assert looks_like_rule_no("TERM") is False
