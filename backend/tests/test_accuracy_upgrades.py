"""审核准确率升级能力单测：三项全部 opt-in，默认零回归。"""
import unittest
from unittest.mock import patch

from app.review_engine import accuracy_upgrades as au


class AccuracyUpgradesTestCase(unittest.TestCase):
    def setUp(self):
        for key in (
            "REVIEW_FULLPAGE_GEOMETRY_HINTS",
            "REVIEW_FULLTEXT_CONSISTENCY_PASS",
            "REVIEW_KEEP_DOWNGRADED_ISSUES",
        ):
            patch.dict("os.environ", {key: ""}, clear=False).start()
        self.addCleanup(patch.stopall)

    # ── 能力1：全页几何提示 ──────────────────────────────────────────
    def test_geometry_hints_default_off(self):
        pages = {"candidates": [{"page_number": 5, "reasons": ["crowded_lines"],
                                 "layout_signals": {"crowding_score": 0.9}}]}
        with patch.dict("os.environ", {"REVIEW_FULLPAGE_GEOMETRY_HINTS": ""}):
            self.assertEqual(au.geometry_hint_issues(pages), [])

    def test_geometry_hints_c3_compliant(self):
        pages = {"candidates": [
            {"page_number": 5, "reasons": ["crowded_lines"], "text_preview": "x",
             "layout_signals": {"crowding_score": 0.9}},
            {"page_number": 9, "reasons": ["crowded_lines"], "text_preview": "y",
             "layout_signals": {"crowding_score": 0.2}},  # 低于阈值
            {"page_number": 12, "reasons": ["image_off_center"], "text_preview": "z",
             "layout_signals": {"image_offset_ratio": 0.4}},
        ]}
        with patch.dict("os.environ", {"REVIEW_FULLPAGE_GEOMETRY_HINTS": "1"}):
            issues = au.geometry_hint_issues(pages, existing_pages={5})  # 5 已被视觉覆盖
        self.assertEqual(len(issues), 1)
        issue = issues[0]
        self.assertEqual(issue["page_number"], 12)
        self.assertLess(issue["confidence"], 85)  # C3
        self.assertTrue(issue["needs_human_review"])

    def test_geometry_hints_never_icon_missing(self):
        pages = {"candidates": [{"page_number": 3, "reasons": ["image_off_center"],
                                 "text_preview": "点击 图标缺失",
                                 "layout_signals": {"image_offset_ratio": 0.5}}]}
        with patch.dict("os.environ", {"REVIEW_FULLPAGE_GEOMETRY_HINTS": "1"}):
            issues = au.geometry_hint_issues(pages)
        self.assertEqual(len(issues), 1)
        self.assertNotIn("图标缺失", issues[0]["suggestion"])

    # ── 能力2：全文一致性索引 ────────────────────────────────────────
    def test_fulltext_index_default_off(self):
        self.assertEqual(au.build_fulltext_consistency_basis("术语一致性 术语一致性"), "")

    def test_fulltext_index_finds_variants(self):
        content = "存储温度 2-8℃。 " * 4 + "储存温度 2-8℃。 " * 4
        with patch.dict("os.environ", {"REVIEW_FULLTEXT_CONSISTENCY_PASS": "1"}):
            basis = au.build_fulltext_consistency_basis(content)
        self.assertIn("术语写法索引", basis)
        self.assertIn("存储/储存", basis)

    def test_fulltext_index_finds_abbreviation(self):
        content = "使用 Catalog Number 字段。" * 3 + "使用 Cat. No. 字段。" * 3
        with patch.dict("os.environ", {"REVIEW_FULLTEXT_CONSISTENCY_PASS": "1"}):
            basis = au.build_fulltext_consistency_basis(content)
        self.assertIn("Catalog Number", basis)

    # ── 能力3：降权保留 ──────────────────────────────────────────────
    def test_downgrade_default_off(self):
        issue = {"rule": "R003", "confidence": 90}
        self.assertIsNone(au.downgrade_instead_of_drop(issue, "noise"))
        self.assertEqual(issue["confidence"], 90)

    def test_downgrade_keeps_marked(self):
        issue = {"rule": "R003", "confidence": 90}
        with patch.dict("os.environ", {"REVIEW_KEEP_DOWNGRADED_ISSUES": "1"}):
            result = au.downgrade_instead_of_drop(issue, "noise")
        self.assertIs(result, issue)
        self.assertEqual(issue["confidence"], 40)
        self.assertTrue(issue["needs_human_review"])
        self.assertEqual(issue["downgrade_reason"], "noise")


if __name__ == "__main__":
    unittest.main()
