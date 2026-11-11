"""2026-11-10 审核准确率提升方案：闸门、A5 错字表、B9 学到的替换对、A9 安全单位。"""

from __future__ import annotations

import collections

from app.review_engine import pipeline as P
from app.review_engine.cn_typo import check_cn_typos
from app.review_engine.learned_patch import check_learned_patches, looks_like_variant
from app.review_engine.unit_spacing import check_safe_tight_unit_gap, check_units_and_spacing


def test_layout_gate_does_not_kill_det_space_unit():
    text = "设置温度为37℃后开始运行。冷却至4 °C 保存。加热至60℃。"
    issues = check_units_and_spacing(text)
    assert issues
    issue = next(item for item in issues if item["rule"] == "DET-SPACE-UNIT")
    assert P.value_score(issue) >= 45
    assert P.is_noise(issue, collections.Counter()) is False
    assert P.select_review_issues([issue])
    blob = P.issue_blob(P.issue_to_mapping(issue))
    hit = P.VISUAL_LAYOUT_PATTERN.search(blob)
    assert hit is None or hit.group(0) not in {"字体", "版式", "layout", "visual"}


def test_true_layout_rules_remain_noise():
    issue = {
        "rule": "STRUCT-LAYOUT-001",
        "category": "表格/版式",
        "severity": "general",
        "source": "rule",
        "confidence": 80,
        "original_text": "列宽不够",
        "suggestion": "拉大列宽",
        "description": "版式问题：列宽溢出单元格",
        "context": "储存环境表格列宽",
        "audit_basis": "版式",
    }
    assert P.is_whitelisted_layout_issue(issue) is False
    assert P.is_noise(issue, collections.Counter()) is True


def test_cn_typo_reports_login_and_neighbor():
    text = "请先登陆系统，仪器应放置于临近热源的涡漩位置。"
    issues = check_cn_typos(text)
    rules = {item["original_text"]: item["expected"] for item in issues}
    assert rules["登陆"] == "登录"
    assert rules["临近"] == "邻近"
    assert rules["涡漩"] == "涡旋"


def test_cn_typo_silent_when_correct():
    assert check_cn_typos("请先登录系统，仪器应放置于邻近热源的涡旋位置。") == []


def test_learned_patch_reports_when_both_forms_present():
    text = "Power off the power. After the run, Power off the device. Repeat Power off the power."
    issues = check_learned_patches(text)
    assert issues
    assert issues[0]["rule"] == "LEARN-PATCH-001"
    blob = issues[0]["original_text"] + issues[0]["suggestion"]
    assert "Power off" in blob


def test_learned_patch_silent_when_only_one_form():
    text = "Power off the device. Then Power off the device again."
    assert check_learned_patches(text) == []


def test_learned_patch_skips_generic_device_product():
    assert looks_like_variant("device", "product") is False
    assert looks_like_variant("Color", "sentence style") is False
    assert looks_like_variant("can store", "can be stored") is True


def test_safe_tight_unit_gap_reports_celsius_and_ml():
    text = "设置温度为37℃后开始运行，加入20mL缓冲液，转速设为3000rpm。"
    issues = check_safe_tight_unit_gap(text)
    originals = " ".join(item["original_text"] for item in issues)
    assert "℃" in originals
    assert "mL" in originals
    assert "rpm" in originals
    assert all(item["rule"] == "DET-SPACE-GAP" for item in issues)


def test_safe_tight_unit_gap_skips_percent():
    assert check_safe_tight_unit_gap("浓度约为5%即可。") == []
