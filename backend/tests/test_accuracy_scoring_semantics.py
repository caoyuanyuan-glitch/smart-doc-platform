"""准确率评分口径自检。

目的：锁定 recall / precision 的语义，防止后续改动悄悄改变匹配口径
（例如放宽匹配会让 recall 虚高，从而"刷"出 88%）。

语义约定：
- recall    = 人工批注中被命中的比例（漏检越多越低）
- precision = 平台检出的问题中真阳性的比例（误报越多越低）
"""

from app.review_engine.annotation_baseline import HumanAnnotation, evaluate_against_annotations


def _annotation(selected_text, rule="DET-TERM-SPELL-001", category="术语拼写"):
    return HumanAnnotation(
        file="doc.pdf",
        page="1",
        annotation_type="批注",
        author="reviewer",
        comment=f"问题：{selected_text}",
        selected_text=selected_text,
        context=f"上下文 {selected_text}",
        category=category,
        layer="deterministic",
        expected_rule=rule,
    )


def _issue(original_text, rule="DET-TERM-SPELL-001", category="术语拼写", issue_id=0):
    return {
        "id": issue_id,
        "source": "rule",
        "rule": rule,
        "category": category,
        "severity": "general",
        "original_text": original_text,
        "suggestion": f"{original_text}（修正）",
        "description": f"命中 {original_text}",
        "audit_basis": "规范",
    }


def test_perfect_match_yields_full_recall_and_precision():
    annotations = [_annotation("线揽"), _annotation("登陆")]
    issues = [_issue("线揽", issue_id=1), _issue("登陆", issue_id=2)]

    result = evaluate_against_annotations(issues, annotations)

    assert result["recall"] == 1.0
    assert result["precision"] == 1.0


def test_missed_annotation_lowers_recall_not_precision():
    """人工批注了 3 条、只命中 1 条：recall 应显著下降。"""
    annotations = [_annotation("线揽"), _annotation("登陆"), _annotation("默认密码")]
    issues = [_issue("线揽", issue_id=1)]

    result = evaluate_against_annotations(issues, annotations)

    assert result["recall"] < 0.5, "漏检应拉低 recall"
    assert result["precision"] == 1.0, "检出的这条是真阳性，precision 不受影响"


def test_extra_unmatched_issue_lowers_precision_not_recall():
    """人工批注全命中，但平台多报了无关问题：precision 应下降。"""
    annotations = [_annotation("线揽")]
    issues = [
        _issue("线揽", issue_id=1),
        _issue("完全无关的其它词", issue_id=2, rule="OTHER-001"),
        _issue("又一个无关词", issue_id=3, rule="OTHER-002"),
    ]

    result = evaluate_against_annotations(issues, annotations)

    assert result["recall"] == 1.0, "批注已全命中，recall 不应受影响"
    assert result["precision"] < 0.5, "大量误报应拉低 precision"


def test_empty_annotation_set_is_handled():
    result = evaluate_against_annotations([_issue("线揽")], [])

    # 无 gold set 时不应崩，且准确率不可知（0 或缺失）
    assert "precision" in result


def test_eighty_eight_boundary_is_meaningful():
    """9 条检出中 8 条真阳性 = 88.9%，刚好过线；7 条 = 77.8%，不达标。

    这条用来说明"问题数变多"不等于"达标"——新增项必须逐条判定 TP/FP。
    """
    annotations = [_annotation(f"问题{i}") for i in range(8)]
    issues_ok = [_issue(f"问题{i}", issue_id=i) for i in range(8)] + [_issue("无关", rule="OTHER", issue_id=99)]
    issues_bad = [_issue(f"问题{i}", issue_id=i) for i in range(8)] + [
        _issue("无关1", rule="OTHER", issue_id=101),
        _issue("无关2", rule="OTHER", issue_id=102),
    ]

    ok = evaluate_against_annotations(issues_ok, annotations)
    bad = evaluate_against_annotations(issues_bad, annotations)

    assert ok["precision"] >= 0.88
    assert bad["precision"] < 0.88
