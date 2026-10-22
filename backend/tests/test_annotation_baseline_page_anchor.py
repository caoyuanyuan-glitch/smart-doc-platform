"""F6 / F6b：页码锚点只用于排除或文本缺失时的二次确认，页级 issue 不走该通道。"""

import json

from app.review_engine.annotation_baseline import (
    HumanAnnotation,
    _issue_blob,
    _matches_annotation_strictly,
)


def _annotation(**kwargs):
    payload = {
        "file": "doc.pdf",
        "page": "1",
        "annotation_type": "Highlight",
        "author": "reviewer",
        "comment": "comment",
        "selected_text": "selected",
        "context": "context text here",
        "category": "交叉引用",
        "layer": "deterministic",
        "expected_rule": "DET-MATERIAL-001",
    }
    payload.update(kwargs)
    return HumanAnnotation(**payload)


def _issue(**kwargs):
    payload = {
        "id": 1,
        "source": "rule",
        "rule": "REF-STYLE",
        "category": "交叉引用",
        "severity": "general",
        "original_text": "Make DNB reaction mixture 1 on Page 66:",
        "suggestion": "the table below",
        "description": "交叉引用写法不规范",
        "audit_basis": "规范",
        "context": "shown in Make DNB reaction mixture 1 on Page 66:",
        "position": json.dumps({"page_number": 12}),
    }
    payload.update(kwargs)
    return payload


def test_text_hit_survives_page_conflict():
    annotation = _annotation(
        page="74",
        selected_text="Make DNB reaction mixture 1 on Page 66:",
        context="Making DNBs Perform the following steps Make DNB reaction mixture 1 on Page 66:",
    )
    issue = _issue(position=json.dumps({"page_number": 12}))
    assert _matches_annotation_strictly(annotation, issue, _issue_blob(issue)) is True


def test_page_anchor_hits_when_text_misses_but_page_matches():
    annotation = _annotation(
        page="12",
        selected_text="zzzznotpresenttoken",
        context="unrelated annotation context without issue tokens here",
        comment="short",
    )
    issue = _issue(
        original_text="completely different wording",
        context="completely different wording",
        description="layout note",
        position=json.dumps({"page_number": 12}),
    )
    assert _matches_annotation_strictly(annotation, issue, _issue_blob(issue)) is True


def test_page_mismatch_without_text_is_not_a_hit():
    annotation = _annotation(
        page="74",
        selected_text="zzzznotpresenttoken",
        context="unrelated annotation context without issue tokens here",
        comment="short",
    )
    issue = _issue(
        original_text="completely different wording",
        context="completely different wording",
        description="layout note",
        position=json.dumps({"page_number": 12}),
    )
    assert _matches_annotation_strictly(annotation, issue, _issue_blob(issue)) is False


def test_page_issue_never_page_anchored():
    annotation = _annotation(
        page="69",
        comment="检查下样式，太挤了",
        selected_text="s\nT",
        context="Tips The manu actual du Reagents or mucos protective",
        category="表格/版式",
        expected_rule="STRUCT-LAYOUT-001",
    )
    issue = _issue(
        rule="PDF-VISUAL-001",
        category="表格/版式",
        original_text="unrelated visual preview without selected tokens",
        description="PDF 页级渲染复核确认疑点",
        context="unrelated visual preview without selected tokens",
        position=json.dumps({"page_number": 69}),
    )
    assert _matches_annotation_strictly(annotation, issue, _issue_blob(issue)) is False
