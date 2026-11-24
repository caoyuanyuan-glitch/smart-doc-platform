"""DET-EN 英文确定性格式规则单测。

每条规则：正例命中 + 反例（正常写法/多数形态/不构成多数）不报。
真实场景样例来自 T7 EN R03 人工批注（2026-11-24 差距分析）：
页码粘连 164for/164to/163in、货号 940-00315900、范围符 20%~80%、
华氏换算 2 ℃ (59 °F to 86 °F)、负温度 -2 ℃。
"""

from __future__ import annotations

from app.review_engine.en_format_consistency import (
    check_catalog_number_digits,
    check_en_format_consistency,
    check_page_reference_glued,
    check_range_separator_style,
    check_suspicious_negative_temperature,
    check_temperature_conversion,
)

RULES = {
    "DET-EN-PAGEGLUE", "DET-EN-CATNO-FMT", "DET-EN-RANGE-SEP",
    "DET-EN-TEMP-CONVERT", "DET-EN-NEG-TEMP",
}


class TestPageReferenceGlued:
    def test_glued_reported(self):
        text = "Refer to the FAQs on page 164for buffer exchange procedures."
        issues = check_page_reference_glued(text)
        assert len(issues) == 1
        assert issues[0]["rule"] == "DET-EN-PAGEGLUE"
        assert "164for" in issues[0]["original_text"]
        assert issues[0]["confidence"] >= 80

    def test_spaced_reference_not_reported(self):
        # 带空格的页码引用（含合法的 page 16 to 20）不报
        text = "See page 164 for details. See pages 16 to 20 for ranges."
        assert check_page_reference_glued(text) == []

    def test_inches_not_reported(self):
        # 无 pages?/see 前缀的数字粘连（如 25in 英寸）不报
        text = "The display measures 25in width and 40cm depth."
        assert check_page_reference_glued(text) == []


class TestCatalogNumberDigits:
    def test_minority_digits_reported(self):
        # 46 处 6 位 vs 1 处 8 位（T7 EN R03 实测比例压缩）
        std = "Cat. No.: 940-003134\n" * 8
        text = std + "Cat. No.: 940-00315900"
        issues = check_catalog_number_digits(text)
        assert len(issues) == 1
        assert issues[0]["rule"] == "DET-EN-CATNO-FMT"
        assert issues[0]["original_text"] == "940-00315900"
        assert "核对" in issues[0]["suggestion"]

    def test_uniform_not_reported(self):
        text = "Cat. No.: 940-003134\n" * 10
        assert check_catalog_number_digits(text) == []

    def test_too_few_samples_not_reported(self):
        # 货号总数不足 6 处时不构成「多数形态」
        text = "Cat. No.: 940-003134\nCat. No.: 940-00315900"
        assert check_catalog_number_digits(text) == []


class TestRangeSeparatorStyle:
    def test_tilde_minority_reported(self):
        # 30 处「to」 vs 1 处「~」（挂人工）
        to_part = "ranges from 2 to 8. " * 15
        text = to_part + "Humidity: 20%~80%, non-condensing."
        issues = check_range_separator_style(text)
        assert len(issues) == 1
        assert issues[0]["rule"] == "DET-EN-RANGE-SEP"
        assert "20%~80%" in issues[0]["original_text"]
        assert issues[0]["needs_human_review"] is True

    def test_all_to_not_reported(self):
        text = "ranges from 2 to 8. " * 10
        assert check_range_separator_style(text) == []

    def test_few_to_not_reported(self):
        # 「to」多数未确立（<5 或不足 4 倍）不报
        text = "range 1~2 mm and 3 to 4 mm"
        assert check_range_separator_style(text) == []


class TestTemperatureConversion:
    def test_wrong_conversion_reported(self):
        # T7 EN R03 p60 实测：2 ℃ 应为 35.6/46.4 ℉，文中 59/86
        text = "2 ℃ to 8 ℃\n(59 °F to 86 °F)\n12 months"
        issues = check_temperature_conversion(text)
        assert len(issues) == 1
        assert issues[0]["rule"] == "DET-EN-TEMP-CONVERT"
        assert "35.6" in issues[0]["suggestion"] and "46.4" in issues[0]["suggestion"]
        assert issues[0]["confidence"] >= 90

    def test_correct_conversion_not_reported(self):
        text = "15 ℃ to 25 ℃ (59 °F to 77 °F) room temperature"
        assert check_temperature_conversion(text) == []

    def test_no_pair_not_reported(self):
        # 只有摄氏范围、无华氏对照时不报
        text = "store at 2 ℃ to 8 ℃ in the refrigerator"
        assert check_temperature_conversion(text) == []


class TestSuspiciousNegativeTemperature:
    def test_single_digit_negative_reported(self):
        text = "Transport temperature: -2 ℃ to 8 ℃"
        issues = check_suspicious_negative_temperature(text)
        assert len(issues) == 1
        assert issues[0]["rule"] == "DET-EN-NEG-TEMP"
        assert issues[0]["needs_human_review"] is True

    def test_freezer_temps_not_reported(self):
        # -20/-80 冷库温度（两位数）不受影响
        text = "Store at -20 ℃ or -80 ℃ for long term."
        assert check_suspicious_negative_temperature(text) == []

    def test_positive_not_reported(self):
        text = "Store at 2 ℃ to 8 ℃."
        assert check_suspicious_negative_temperature(text) == []


class TestEntry:
    def test_entry_aggregates_all_rules(self):
        text = (
            "See page 164for details. " * 1
            + "Cat. No.: 940-003134\n" * 8
            + "Cat. No.: 940-00315900\n"
            + "2 ℃ to 8 ℃\n(59 °F to 86 °F)\n"
        )
        issues = check_en_format_consistency(text)
        got = {i["rule"] for i in issues}
        assert {"DET-EN-PAGEGLUE", "DET-EN-CATNO-FMT", "DET-EN-TEMP-CONVERT"} <= got
        assert got <= RULES

    def test_empty_text(self):
        assert check_en_format_consistency("") == []
        assert check_en_format_consistency(None) == []
