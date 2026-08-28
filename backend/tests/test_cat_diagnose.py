import asyncio
import os
import unittest
from unittest.mock import patch


class CatDiagnoseMappingTest(unittest.TestCase):
    def test_map_by_type_then_rule_name(self):
        from app.utils.cat_diagnose import map_rule_to_category

        self.assertEqual(map_rule_to_category({"type": "term", "rule_name": "术语替换"}), ("term", "high"))
        self.assertEqual(map_rule_to_category({"type": "typo"}), ("spelling", "high"))
        self.assertEqual(map_rule_to_category({"type": "imperative"}), ("register", "low"))
        self.assertEqual(map_rule_to_category({"type": "format"}), ("spelling", "low"))
        self.assertEqual(map_rule_to_category({"type": "punctuation"}), ("spelling", "low"))
        self.assertEqual(map_rule_to_category({"type": "forbidden_words"}), ("word", "high"))
        self.assertEqual(map_rule_to_category({"type": "double_negative"}), ("logic", "medium"))
        self.assertEqual(map_rule_to_category({"type": "passive_voice"}), ("syntax", "low"))
        self.assertEqual(map_rule_to_category({"rule_name": "中英文空格"}), ("spelling", "low"))
        self.assertEqual(map_rule_to_category(rule_source="sentence_guide"), ("syntax", "low"))
        self.assertEqual(map_rule_to_category(rule_source="surface_rules"), ("word", "medium"))
        self.assertEqual(map_rule_to_category({"type": "unknown-rule"}), ("other", "low"))

    def test_annotate_does_not_overwrite_existing_fields(self):
        from app.utils.cat_diagnose import annotate_cat_candidates

        items = [{
            "candidates": [
                {"rule_source": "sentence_guide", "template_text": "A", "category": "term", "severity": "high"},
                {"rule_source": "surface_rules", "template_text": "B"},
            ]
        }]
        annotate_cat_candidates(items)
        self.assertEqual(items[0]["candidates"][0]["category"], "term")
        self.assertEqual(items[0]["candidates"][0]["severity"], "high")
        self.assertEqual(items[0]["candidates"][1]["category"], "word")
        self.assertEqual(items[0]["candidates"][1]["severity"], "medium")


class CatDiagnoseMergeTest(unittest.TestCase):
    def test_local_priority_and_different_category_kept(self):
        from app.utils.cat_diagnose import merge_local_and_diagnoses

        cat_items = [{
            "sentence_index": 0,
            "original_text": "将样本加载到流道池后进行孵育。",
            "candidates": [{
                "template_text": "将样本加载到 flow cell 后进行孵育。",
                "category": "term",
                "severity": "high",
                "template_id": "t1",
            }],
        }]
        diagnoses = [
            {
                "sentence_index": 0,
                "quote": "将样本加载到流道池后进行孵育。",
                "category": "term",
                "severity": "medium",
                "problem": "术语不规范",
                "revised": "将样本加载到 flow cell 后进行孵育。",
                "rationale": "手册统一",
            },
            {
                "sentence_index": 0,
                "quote": "进行孵育",
                "category": "risk",
                "severity": "high",
                "problem": "未说明孵育温度",
                "revised": "在 37℃ 进行孵育",
                "rationale": "缺少关键参数",
            },
        ]
        merged, kept = merge_local_and_diagnoses(cat_items, diagnoses, cat_items)
        categories = [c.get("category") for c in merged[0]["candidates"]]
        self.assertIn("term", categories)
        self.assertIn("risk", categories)
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]["category"], "risk")


class CatDiagnoseSwitchTest(unittest.TestCase):
    def test_switch_off_skips_ai_and_returns_empty(self):
        from app.utils import cat_diagnose

        called = {"count": 0}

        def boom(_prompt):
            called["count"] += 1
            raise AssertionError("switch off should not call AI")

        with patch.dict(os.environ, {"AI_DIAGNOSE_ENABLED": "false"}, clear=False):
            with patch.object(cat_diagnose, "_chat_diagnose", side_effect=boom):
                result = asyncio.run(cat_diagnose.open_diagnose_sentences(
                    [{"sentence_index": 0, "text": "将样本加载到流道池后进行孵育。"}],
                    {},
                    "",
                    "",
                ))
        self.assertEqual(result, [])
        self.assertEqual(called["count"], 0)

    def test_json_fallback_extracts_object(self):
        from app.utils.cat_diagnose import extract_json_object, parse_diagnoses_payload

        payload = extract_json_object('note {"diagnoses": []} trailing')
        self.assertEqual(payload, {"diagnoses": []})
        parsed = parse_diagnoses_payload({
            "diagnoses": [{
                "sentence_index": 1,
                "quote": "流道池",
                "category": "term",
                "severity": "high",
                "problem": "非标准名",
                "revised": "flow cell",
                "rationale": "手册",
            }]
        }, allowed_indexes={1})
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["category"], "term")


if __name__ == "__main__":
    unittest.main()
