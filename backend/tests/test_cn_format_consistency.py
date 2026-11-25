"""DET-CN 中文确定性格式规则单测。

每条规则：正例命中 + 反例（全文一致/多数形态/正常写法）不报。
真实 goldset 场景样例来自 T7 R01 人工批注（#3/#6/#10/#15/#33）。
"""

from __future__ import annotations

import pytest

from app.review_engine.cn_format_consistency import (
    check_catalog_number_format,
    check_cn_format_consistency,
    check_colon_comma,
    check_line_leading_punct,
    check_redundant_over_above,
    check_tight_degree_unit,
)


RULES = {i["rule"] for i in [
    {"rule": "DET-CN-UNITSPACE"}, {"rule": "DET-CN-CATNO-FMT"},
    {"rule": "DET-CN-REDUNDANT"}, {"rule": "DET-CN-PUNCT-CLUSTER"},
    {"rule": "DET-CN-LINE-LEAD"},
]}


class TestTightDegreeUnit:
    def test_tight_minority_reported(self):
        # 全文 144 处带空格、2 处紧贴（T7 R01 p64 实测比例）→ 报紧贴的
        text = "试剂储存在 2 ℃~8 ℃环境中。" * 20 + "测序载片可在2℃~8℃与室温最多切换3 次。"
        issues = check_tight_degree_unit(text)
        assert issues and all(i["rule"] == "DET-CN-UNITSPACE" for i in issues)
        assert all("2℃" in i["original_text"] or "8℃" in i["original_text"] for i in issues)

    def test_uniform_tight_not_reported(self):
        # 全文一致紧贴 → 风格统一，不报
        text = "储存在2℃~8℃环境中。" * 30
        assert check_tight_degree_unit(text) == []

    def test_only_spaced_not_reported(self):
        text = "储存在 2 ℃~8 ℃环境中。" * 30
        assert check_tight_degree_unit(text) == []

    def test_mixed_usage_reported_even_if_spaced_few(self):
        # 2026-11-24 口径更新（T7RS R01 Tina p41/p64 裁定）：数字与单位间加空格
        # 是硬规范，全文混用（哪怕带空格仅 1 处）即不一致，紧贴处要报。
        # 旧的「带空格 ≥5 且 ≥4×紧贴」多数派门槛已废弃。
        text = " 2 ℃ 环境以及2℃ 紧贴"
        issues = check_tight_degree_unit(text)
        assert len(issues) == 1
        assert issues[0]["original_text"] == "2℃"


class TestCatalogNumberFormat:
    def test_deviant_format_reported(self):
        std = "DNBSEQ-T7+RS 插件试剂盒（T7+ FCL PE100）货号：940-001530-00。\n" * 8
        text = std + "DNBSEQ-T7+RS 插件试剂盒2（T7+ FCL PE100） 货号：940-00317100"
        issues = check_catalog_number_format(text)
        assert len(issues) == 1
        assert issues[0]["rule"] == "DET-CN-CATNO-FMT"
        assert issues[0]["original_text"] == "940-00317100"
        # 不推断正确货号，只建议核对
        assert "核对" in issues[0]["suggestion"]

    def test_all_standard_not_reported(self):
        text = "货号：940-001530-00。\n" * 10
        assert check_catalog_number_format(text) == []

    def test_few_standard_not_reported(self):
        # 标准形态不足 5 处，不构成多数写法
        text = "货号：940-001530-00。\n货号：940-001530-00。\n货号：940-00317100"
        assert check_catalog_number_format(text) == []

    def test_standard_form_not_double_reported(self):
        # 带尾段的标准形态不得被 DEV 正则误捕
        text = "货号：940-001530-00。\n" * 8 + "货号：940-00153000"
        issues = check_catalog_number_format(text)
        assert all(i["original_text"] == "940-00153000" for i in issues)


class TestRedundantOverAbove:
    def test_redundant_reported(self):
        text = "超过5 天以上未使用或超过14 天以上未进行维护清洗时，均显示红色圆点。"
        issues = check_redundant_over_above(text)
        assert len(issues) == 2
        assert issues[0]["rule"] == "DET-CN-REDUNDANT"
        assert "超过5 天以上" in issues[0]["original_text"]

    def test_over_only_not_reported(self):
        assert check_redundant_over_above("超过 5 天未使用时需清洗。") == []

    def test_above_only_not_reported(self):
        assert check_redundant_over_above("5 天以上未使用时需清洗。") == []

    def test_cross_sentence_not_overmatch(self):
        # 「以上」若在句号之后，不得跨句匹配
        text = "超过 5 天未使用。以上要求适用于所有模块。"
        assert check_redundant_over_above(text) == []


class TestColonComma:
    def test_colon_comma_reported(self):
        text = "请按照第56 页“文库浓度要求”中的步骤对文库进行浓缩处理：，以下步骤中所用的磁珠需按量加入。"
        issues = check_colon_comma(text)
        assert len(issues) == 1
        assert issues[0]["rule"] == "DET-CN-PUNCT-CLUSTER"
        assert issues[0]["original_text"].startswith("：")

    def test_halfwidth_reported(self):
        assert len(check_colon_comma("配置如下:, 2号孔为空白对照。")) == 1

    def test_normal_colon_not_reported(self):
        assert check_colon_comma("配置如下：2 号孔为空白对照。") == []


class TestLineLeadingPunct:
    def test_leading_punct_reported(self):
        text = "第一行正文内容\n，可按照文库投入量进行混合。"
        issues = check_line_leading_punct(text)
        assert len(issues) == 1
        assert issues[0]["rule"] == "DET-CN-LINE-LEAD"
        # 置信度 70 → 自动挂 needs_human_review（50-74 区间）
        assert 50 <= issues[0]["confidence"] < 75

    def test_normal_lines_not_reported(self):
        assert check_line_leading_punct("第一行正文。\n第二行正文。") == []

    def test_indented_leading_punct_reported(self):
        assert len(check_line_leading_punct("正文行\n　　。句首句号")) == 1


class TestEntry:
    def test_entry_aggregates_all(self):
        spaced_deg = "储存在 2 ℃~8 ℃。" * 8
        std_catno = "货号：940-001530-00。\n" * 8
        text = (
            "超过5 天以上未使用。"
            + spaced_deg + "紧贴样例2℃出现。"
            + "处理：，后续步骤。\n，回车残留标点。"
            + std_catno + "货号：940-00317100"
        )
        rules = {i["rule"] for i in check_cn_format_consistency(text)}
        assert rules == RULES

    def test_empty_input(self):
        assert check_cn_format_consistency("") == []
        assert check_cn_format_consistency(None) == []  # type: ignore[arg-type]
