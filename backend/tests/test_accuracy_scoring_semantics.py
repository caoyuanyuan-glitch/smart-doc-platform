"""准确率评分口径自检。

目的：锁定 recall / precision 的语义，防止后续改动悄悄改变匹配口径
（例如放宽匹配会让 recall 虚高，从而"刷"出 88%）。

语义约定：
- recall    = 人工批注中被命中的比例（漏检越多越低）
- precision = 平台检出的问题中真阳性的比例（误报越多越低）
"""

import json

from app.review_engine.annotation_baseline import (
    HumanAnnotation,
    _issue_blob,
    _matches_annotation_strictly,
    evaluate_against_annotations,
)


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


def test_strict_recall_is_injective():
    """一条平台问题不得同时命中多条人工批注（strict 与 recall 同口径）。

    复现场景：人工批注 3 条、文本均与同一条平台问题重叠，平台只报 1 条问题。
    旧实现 strict 用 any() 判定，strict_recall 会虚高成 1.0；修复后必须为 1/3。
    """
    text = "聚散球磁珠法核酸提取试剂"
    annotations = [_annotation(text), _annotation(text), _annotation(text)]
    issues = [_issue(text, issue_id=1)]

    result = evaluate_against_annotations(issues, annotations)

    assert result["recall"] == round(1 / 3, 4)
    assert result["strict_recall"] == round(1 / 3, 4), "strict_recall 不得非单射虚高"
    assert result["strict_matched"] == 1


def test_strict_recall_perfect_when_matches_are_one_to_one():
    """正常场景回归：3 条问题各对应 1 条批注时，strict 仍应满分。"""
    texts = ["聚散球磁珠法核酸提取试剂", "测序接头连接缓冲液", "文库定量荧光染料"]
    annotations = [_annotation(text) for text in texts]
    issues = [_issue(text, issue_id=index + 1) for index, text in enumerate(texts)]

    result = evaluate_against_annotations(issues, annotations)

    assert result["strict_recall"] == 1.0
    assert result["strict_precision"] == 1.0
    assert result["strict_matched"] == 3


def test_goldset_expected_rule_matches_platform_rule_id_exactly():
    annotations = [_annotation("before clean", rule="DOC-GRAM-002", category="语法与表达")]
    issues = [_issue("before clean", rule="DOC-GRAM-002", category="语法与表达", issue_id=1)]

    result = evaluate_against_annotations(issues, annotations)

    assert result["recall"] == 1.0
    assert result["precision"] == 1.0
    assert result["strict_recall"] == 1.0


def test_exact_rule_id_without_text_overlap_is_not_a_hit():
    """规则号相同但原文与批注无 token 重叠时，不得算命中。"""
    annotation = HumanAnnotation(
        file="doc.pdf",
        page="1",
        annotation_type="批注",
        author="reviewer",
        comment="介词后 clean 应为 cleaning",
        selected_text="before clean",
        context="Before clean the instrument, power it down completely.",
        category="语法与表达",
        layer="deterministic",
        expected_rule="DOC-GRAM-002",
    )
    issue = {
        "id": 99,
        "source": "rule",
        "rule": "DOC-GRAM-002",
        "category": "语法与表达",
        "severity": "general",
        "original_text": "completely unrelated cartridge parking sequence",
        "suggestion": "unrelated suggestion",
        "description": "unrelated description",
        "audit_basis": "规范",
        "context": "dummy run parking sequence on an empty deck",
    }

    assert _matches_annotation_strictly(annotation, issue, _issue_blob(issue)) is False
    result = evaluate_against_annotations([issue], [annotation])
    assert result["strict_recall"] == 0.0


def test_manual_review_ratio_uses_same_strict_pool():
    """manual_review_ratio 与 strict_precision 共用同一 issue 池，不另开匹配通道。"""
    annotations = [_annotation("聚散球磁珠法核酸提取试剂")]
    issues = [
        _issue("聚散球磁珠法核酸提取试剂", issue_id=1),
        {
            **_issue("无关视觉占位文本", rule="PDF-VISUAL-001", category="表格/版式", issue_id=2),
            "needs_human_review": True,
        },
        {
            **_issue("另一无关占位文本", rule="PDF-VISUAL-001", category="表格/版式", issue_id=3),
            "position": json.dumps({"needs_human_review": True}),
        },
    ]

    result = evaluate_against_annotations(issues, annotations)

    assert result["issue_total"] == 3
    assert result["strict_precision"] == round(1 / 3, 4)
    assert result["manual_issue_count"] == 2
    assert result["manual_review_ratio"] == round(2 / 3, 4)
    assert result["strict_recall"] == 1.0
    assert result["recall"] == 1.0
