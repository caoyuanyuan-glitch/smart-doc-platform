"""AI 产出（无规则号）issue 的预置误报匹配测试。

背景：原预置误报模式只按 rule_family 匹配，AI 深度审核产出的 issue
rule 为空 → rule_family('')='' → 全部跳过（实测 T7 图标类 9 条命中 0 条）。
FP-HUMAN-ICON-001 用 allow_empty_family 支持这类 issue，且仅精确匹配
"缺少可点击对象"特征，不误伤有规则号的正当 issue。
"""
from app.review_engine.false_positive_fingerprint import match_preset_pattern


def _issue(rule="", description="", category="术语一致性", original_text=None, suggestion=None):
    return {
        "rule": rule,
        "original_text": original_text if original_text is not None else "点击测序主界面右上角的 >【测序方案】",
        "suggestion": suggestion if suggestion is not None else "点击右上角对应图标 >【测序方案】",
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


# ---- goldset6 人工裁定回流（2026-11-25）四类模式 ----

def test_g6_ui_object_missing_marked():
    issue = _issue(description="UI 对象缺失，用户无法判断点击对象")
    assert match_preset_pattern(issue, language="zh") == "FP-G6-ICON-UI-001"
    issue_en = _issue(description="UI object missing: user cannot know which button/icon to use")
    assert match_preset_pattern(issue_en, language="en") == "FP-G6-ICON-UI-001"


def test_g6_table_run_artifact_marked():
    issue = _issue(
        category="格式排版",
        original_text="试剂瓶水浴解冻时长 （h） 20 ℃ ≤ 水浴温度 ≤ 30 ℃ 3 1.5",
        description="表格内容与表头对应关系不清晰，无法判断哪个温度对应哪个时长",
    )
    assert match_preset_pattern(issue, language="zh") == "FP-G6-TABLE-RUN-001"


def test_g6_term_assertion_marked_but_glossary_violation_not():
    assert_match = _issue(
        description="“试剂槽”应为“试剂仓”（仪器部件术语）",
        suggestion="完成载片和试剂仓装载",
    )
    assert match_preset_pattern(assert_match, language="zh") == "FP-G6-TERM-KB-001"
    # 与术语库冲突的真问题不得命中
    real = _issue(description="与术语库不一致：该部件在术语库中标注为进样仓")
    assert match_preset_pattern(real, language="zh") is None


def test_g6_proc_date_blank_marked_but_date_error_not():
    blank = _issue(category="信息完整", original_text="批准日期 生效日期 修改日期",
                   description="批准日期、生效日期、修改日期均未填写具体日期")
    assert match_preset_pattern(blank, language="zh") == "FP-G6-PROC-DATE-001"
    real = _issue(category="信息完整", description="生效日期早于批准日期，日期逻辑矛盾")
    assert match_preset_pattern(real, language="zh") is None


def test_g6_rule_numbered_issue_not_hit_by_g6_patterns():
    """G6 系列仅限 AI 产出（无规则号），不得误伤规则引擎的真问题。"""
    issue = _issue(rule="DOC-FMT-003", description="UI 对象缺失，用户无法判断点击对象")
    assert match_preset_pattern(issue, language="zh") != "FP-G6-ICON-UI-001"
