import json
import os
from pathlib import Path

from app.review_engine.annotation_baseline import (
    HumanAnnotation,
    _issue_blob,
    _load_families,
    _matches_expected_rule,
    _matches_expected_rule_data,
    _matches_expected_rule_legacy,
    reset_families_cache,
)

ASSETS = Path(__file__).resolve().parents[1] / "app" / "review_engine" / "assets"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "regression_701_rules.jsonl"


def _ann(rule, **kwargs):
    payload = {
        "file": "doc.pdf",
        "page": "1",
        "annotation_type": "Highlight",
        "author": "r",
        "comment": kwargs.pop("comment", "comment"),
        "selected_text": kwargs.pop("selected_text", "selected"),
        "context": kwargs.pop("context", "context"),
        "category": "cat",
        "layer": "deterministic",
        "expected_rule": rule,
    }
    payload.update(kwargs)
    return HumanAnnotation(**payload)


def _issue(**kwargs):
    payload = {
        "rule": "X",
        "category": "其他",
        "original_text": "orig",
        "suggestion": "",
        "description": "",
        "context": "",
        "audit_basis": "",
    }
    payload.update(kwargs)
    return payload


def test_asset_files_exist():
    assert (ASSETS / "expected_rule_families.json").is_file()
    assert (ASSETS / "rule_corpus_fewshot.jsonl").is_file()
    assert (ASSETS / "rule_candidates_20261106.xlsx").is_file()
    assert FIXTURE.is_file()
    families = json.loads((ASSETS / "expected_rule_families.json").read_text(encoding="utf-8"))
    assert families["stats"]["total"] == 68
    assert families["stats"]["in_legacy_code"] == 24
    assert families["stats"]["legacy_only"] == 9
    assert families["stats"]["new_rules"] == 44
    assert families["stats"]["disabled"] == 44
    assert families["stats"]["in_regression_set"] == 52
    assert sum(1 for _ in FIXTURE.open(encoding="utf-8")) == 1061


def test_new_rules_are_disabled_and_do_not_match():
    reset_families_cache()
    item = _ann("STRUCT-NUM-STYLE-001", comment="MGI的写不写")
    issue = _issue(rule="CYY-CN-FMT-001", category="数字 单位空格")
    blob = _issue_blob(issue)
    assert _matches_expected_rule_data(item, issue, blob) is False


def test_platform_rules_default_off(monkeypatch):
    reset_families_cache()
    monkeypatch.delenv("WORKBUDDY_RULE_PLATFORM_CH", raising=False)
    families = _load_families()
    entry = families["AI-STYLE-001"]
    assert entry.get("platform_rules")
    item = _ann("AI-STYLE-001")
    issue = _issue(rule=entry["platform_rules"][0], category="无关分类")
    blob = _issue_blob(issue)
    assert _matches_expected_rule_data(item, issue, blob) is False
    monkeypatch.setenv("WORKBUDDY_RULE_PLATFORM_CH", "on")
    assert _matches_expected_rule_data(item, issue, blob) is True
    monkeypatch.setenv("WORKBUDDY_RULE_PLATFORM_CH", "off")


def test_auto_mode_uses_data_when_assets_exist(monkeypatch):
    reset_families_cache()
    monkeypatch.setenv("WORKBUDDY_RULE_FAMILIES", "auto")
    item = _ann("DET-CN-001")
    issue = _issue(rule="ENG-CN-001", category="x")
    blob = _issue_blob(issue)
    assert _matches_expected_rule(item, issue, blob) is True


def test_legacy_and_data_probes_are_equivalent():
    reset_families_cache()
    probes = [
        ("DET-REVISION-001", _issue(rule="DOC-REV-1"), {}),
        ("DET-REVISION-001", _issue(rule="CYY-CN-REVISION-9"), {}),
        ("DET-REVISION-001", _issue(rule="X", category="版本记录"), {}),
        ("DET-REVISION-001", _issue(rule="X", category="修订一致性"), {}),
        ("DET-CN-001", _issue(rule="ENG-CN-001"), {}),
        ("DET-CN-001", _issue(rule="X", category="中文混入"), {}),
        ("STRUCT-SCOPE-001", _issue(rule="DOC-SCOPE-001"), {}),
        ("STRUCT-SCOPE-001", _issue(rule="X", original_text="ne384 硬件配置"), {}),
        ("STRUCT-FIGTAB-001", _issue(rule="DOC-FIGTAB-01"), {}),
        ("STRUCT-FIGTAB-001", _issue(rule="X", category="表图编号"), {}),
        ("STRUCT-LAYOUT-001", _issue(rule="CYY-CN-LAYOUT-1"), {}),
        ("STRUCT-LAYOUT-001", _issue(rule="X", category="表格/版式"), {}),
        ("STRUCT-LAYOUT-001", _issue(rule="X", original_text="储存环境"), {"comment": "列宽不对"}),
        ("STRUCT-IMAGE-001", _issue(rule="CYY-CN-IMAGE-1"), {}),
        ("STRUCT-IMAGE-001", _issue(rule="PDF-VISUAL-001"), {}),
        ("STRUCT-IMAGE-001", _issue(rule="X", category="图片丢失"), {}),
        ("STRUCT-IMAGE-001", _issue(rule="CYY-CN-LOGIC-007"), {"comment": "install finish 打开本系统"}),
        ("STRUCT-IMAGE-001", _issue(rule="X", category="内容逻辑"), {"comment": "install finish 打开本系统"}),
        ("STRUCT-STEP-001", _issue(rule="CYY-CN-STRUCT-001"), {}),
        ("STRUCT-STEP-001", _issue(rule="X", category="步骤结构"), {}),
        ("STRUCT-COMPONENT-001", _issue(rule="CYY-CN-ROHS-1"), {}),
        ("STRUCT-COMPONENT-001", _issue(rule="X", category="结构完整"), {}),
        ("STRUCT-INDEX-001", _issue(rule="CYY-CN-INDEX-1"), {}),
        ("STRUCT-INDEX-001", _issue(rule="X", category="索引"), {}),
        ("AI-PROC-001", _issue(rule="DOC-PROC-001"), {}),
        ("AI-PROC-001", _issue(rule="X", category="操作步骤语气"), {}),
        ("DET-TITLE-CASE-001", _issue(rule="DOC-TITLE-001"), {}),
        ("DET-TITLE-CASE-001", _issue(rule="X", category="标题大小写"), {}),
        ("AI-CHECK-001", _issue(rule="DOC-POS-001"), {"comment": "pos"}),
        ("AI-CHECK-001", _issue(rule="CYY-CN-CHECK-1"), {}),
        ("AI-CHECK-001", _issue(rule="X", category="人工确认"), {}),
        ("AI-ADDR-001", _issue(rule="CYY-CN-ADDR-1"), {}),
        ("AI-ADDR-001", _issue(rule="X", category="地址"), {}),
        ("STRUCT-PAGE-NUM-001", _issue(rule="CYY-CN-PAGE-1"), {}),
        ("STRUCT-PAGE-NUM-001", _issue(rule="X", category="页码"), {}),
        ("DET-SPACE-001", _issue(rule="DOC-SPACE-006"), {}),
        ("DET-SPACE-001", _issue(rule="X", category="空格"), {}),
        ("DET-PUNCT-001", _issue(rule="DOC-PUNCT-002"), {}),
        ("DET-PUNCT-001", _issue(rule="X", category="标点"), {}),
        ("DET-CATNO-001", _issue(rule="DOC-CATNO-1"), {}),
        ("DET-CATNO-001", _issue(rule="X", category="货号"), {}),
        ("DET-MATERIAL-001", _issue(rule="CYY-CN-REF-003"), {}),
        ("DET-MATERIAL-001", _issue(rule="X", category="交叉引用"), {}),
        ("DET-TYPO-001", _issue(rule="CYY-CN-LAYOUT-2"), {}),
        ("DET-TYPO-001", _issue(rule="X", category="字体/版式"), {}),
        ("DOC-DATA-001", _issue(rule="DOC-DATA-001"), {}),
        ("DOC-DATA-001", _issue(rule="X", category="信息完整性"), {}),
        ("DET-TERM-SPELL-001", _issue(rule="SPELL-TRANS"), {}),
        ("DET-TERM-SPELL-001", _issue(rule="X", category="拼写错误"), {}),
        ("STRUCT-DUP-001", _issue(rule="DOC-DUP-1"), {}),
        ("STRUCT-DUP-001", _issue(rule="X", category="重复"), {}),
        ("STRUCT-TERM-001", _issue(rule="DOC-TERM-1"), {}),
        ("STRUCT-TERM-001", _issue(rule="X", category="术语一致性"), {}),
        ("AI-STYLE-001", _issue(rule="DOC-MICRO-001"), {}),
        ("AI-STYLE-001", _issue(rule="X", category="表达与句式"), {}),
        ("DET-CN-001", _issue(rule="NOPE", category="其他"), {}),
    ]
    covered = set()
    mismatch = []
    for expected, issue, extra in probes:
        item = _ann(expected, **extra)
        blob = _issue_blob(issue)
        old = _matches_expected_rule_legacy(item, issue, blob)
        new = _matches_expected_rule_data(item, issue, blob)
        if old:
            covered.add(expected)
        if old != new:
            mismatch.append((expected, issue.get("rule"), issue.get("category"), old, new))
    assert mismatch == []
    assert len(covered) == 24


def test_data_mode_raises_when_assets_missing(monkeypatch, tmp_path):
    import app.review_engine.annotation_baseline as baseline

    monkeypatch.setattr(baseline, "_FAMILIES_FILE", tmp_path / "missing.json")
    monkeypatch.setattr(baseline, "_FAMILIES_CACHE", None)
    monkeypatch.setenv("WORKBUDDY_RULE_FAMILIES", "data")
    item = _ann("DET-CN-001")
    issue = _issue(rule="ENG-CN-001")
    try:
        raised = False
        try:
            _matches_expected_rule(item, issue, _issue_blob(issue))
        except RuntimeError:
            raised = True
        assert raised
    finally:
        monkeypatch.setenv("WORKBUDDY_RULE_FAMILIES", "auto")
        reset_families_cache()
