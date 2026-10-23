import unittest


class NumberSpaceRuleTest(unittest.TestCase):
    def test_compact_range_and_ratio_are_detected(self):
        from app.utils.polish_rules_engine import detect_number_unit_spacing, fix_number_unit_spacing

        range_text = "加入 50~200·ng DNA。"
        range_issues = detect_number_unit_spacing(range_text)
        self.assertTrue(range_issues)
        self.assertEqual(range_issues[0]["original"], "50~200·ng")
        self.assertEqual(range_issues[0]["replacement"], "50 ~ 200 ng")
        self.assertEqual(fix_number_unit_spacing(range_text, range_issues), "加入 50 ~ 200 ng DNA。")

        ratio_text = "OD260/OD280=1.8"
        ratio_issues = detect_number_unit_spacing(ratio_text)
        self.assertTrue(ratio_issues)
        self.assertEqual(ratio_issues[0]["original"], "OD260/OD280=1.8")
        self.assertEqual(ratio_issues[0]["replacement"], "OD260 / OD280 = 1.8")
        self.assertEqual(fix_number_unit_spacing(ratio_text, ratio_issues), "OD260 / OD280 = 1.8")

    def test_plain_number_unit_still_works(self):
        from app.utils.polish_rules_engine import detect_number_unit_spacing

        issues = detect_number_unit_spacing("体积为25mg。")
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["replacement"], "25 mg")

    def test_format_rule_applies_replacement(self):
        from types import SimpleNamespace
        from app.utils.polish_rules_engine import apply_custom_rules

        rule = SimpleNamespace(
            id=9,
            match_pattern="流道池",
            replacement_text="流道槽",
            rule_type="format_rule",
            rule_name="流道池",
            description="diagnose import",
        )
        polished, issues = apply_custom_rules("将样本加入流道池中。", [rule])
        self.assertEqual(polished, "将样本加入流道槽中。")
        self.assertEqual(len(issues), 1)


if __name__ == "__main__":
    unittest.main()
