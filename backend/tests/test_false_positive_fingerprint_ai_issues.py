"""AI 产出（无规则号）issue 的预置误报匹配测试。

背景：原预置误报模式只按 rule_family 匹配，AI 深度审核产出的 issue
rule 为空 → rule_family('')='' → 全部跳过（实测 T7 图标类 9 条命中 0 条）。
FP-HUMAN-ICON-001 用 allow_empty_family 支持这类 issue，且仅精确匹配
"缺少可点击对象"特征，不误伤有规则号的正当 issue。
"""
from app.review_engine.false_positive_fingerprint import match_preset_pattern


def _issue(rule="", description="", category="术语一致性"):
    return {
        "rule": rule,
        "original_text": "点击测序主界面右上角的 >【测序方案】",
        "suggestion": "点击右上角对应图标 >【测序方案】",
        "description": description,
        "context": "",
        "category": category,
    }


def test_ai_icon_artifact_is_marked():
    issue = _issue(description="“右上角的 ”后缺少可点击对象（图标/按钮），用户无法判断点击什么")
    assert match_preset_pattern(issue, language="zh") == "FP-HUMAN-ICON-001"


def test_rule_based_issue_not_false_positive():
    """有规则号的正当 issue 不得被 AI 误报模式命中。"""
    issue = _issue(rule="DOC-FMT-003", description="缺少可点击对象（图标/按钮）")
    assert match_preset_pattern(issue, language="zh") != "FP-HUMAN-ICON-001"


def test_unrelated_issue_not_marked():
    issue = _issue(description="术语大小写与全文不一致")
    assert match_preset_pattern(issue, language="zh") != "FP-HUMAN-ICON-001"
