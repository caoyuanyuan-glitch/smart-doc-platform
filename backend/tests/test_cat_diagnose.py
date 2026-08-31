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

    def test_hint_only_empty_revised_is_kept(self):
        from app.utils.cat_diagnose import merge_local_and_diagnoses

        cat_items = [{
            "sentence_index": 1,
            "original_text": "另一句。",
            "candidates": [{
                "template_text": "另一句。",
                "category": "term",
                "severity": "high",
            }],
        }]
        diagnoses = [{
            "sentence_index": 0,
            "quote": "请勿关闭电源，关闭电源后再进行维护。",
            "category": "logic",
            "severity": "high",
            "problem": "前后指令冲突",
            "revised": "",
            "rationale": "无法忠实改写",
        }]
        sentence_items = [
            {"sentence_index": 0, "text": "请勿关闭电源，关闭电源后再进行维护。"},
            {"sentence_index": 1, "text": "另一句。"},
        ]
        merged, kept = merge_local_and_diagnoses(cat_items, diagnoses, sentence_items)
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]["category"], "logic")
        self.assertEqual(kept[0]["revised"], "")
        logic_items = [item for item in merged if item.get("sentence_index") == 0]
        self.assertEqual(len(logic_items), 1)
        self.assertEqual(logic_items[0]["candidates"][0]["problem"], "前后指令冲突")


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

    def test_silent_normalize_paths_log_reason(self):
        from app.utils.cat_diagnose import parse_diagnoses_payload

        payload = {
            "diagnoses": [
                "bad",
                {
                    "sentence_index": "x",
                    "quote": "q",
                    "category": "term",
                    "severity": "high",
                    "problem": "p",
                    "revised": "r",
                },
                {
                    "sentence_index": 9,
                    "quote": "q",
                    "category": "term",
                    "severity": "high",
                    "problem": "p",
                    "revised": "r",
                },
                {
                    "sentence_index": 0,
                    "quote": "q",
                    "category": "clarity",
                    "severity": "high",
                    "problem": "p",
                    "revised": "r",
                },
                {
                    "sentence_index": 1,
                    "quote": "流道池",
                    "category": "term",
                    "severity": "high",
                    "problem": "非标准名",
                    "revised": "flow cell",
                },
            ]
        }
        with self.assertLogs("app.utils.cat_diagnose", level="INFO") as cm:
            parsed = parse_diagnoses_payload(payload, allowed_indexes={0, 1})
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["sentence_index"], 1)
        text = "\n".join(cm.output)
        self.assertIn("reason=bad_shape", text)
        self.assertIn("reason=bad_index", text)
        self.assertIn("reason=index_not_allowed", text)
        self.assertIn("reason=bad_category", text)
        self.assertIn("clarity", text)

    def test_index_from_other_unmatched_batch_is_kept(self):
        from app.utils.cat_diagnose import parse_diagnoses_payload

        parsed = parse_diagnoses_payload({
            "diagnoses": [{
                "sentence_index": 20,
                "quote": "跨批句子",
                "category": "term",
                "severity": "high",
                "problem": "术语",
                "revised": "term",
            }]
        }, allowed_indexes={0, 1, 20})
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["sentence_index"], 20)


class CatDiagnoseIconPlaceholderTest(unittest.TestCase):
    def test_missing_icon_placeholder_is_dropped(self):
        from app.utils.cat_diagnose import parse_diagnoses_payload

        with self.assertLogs("app.utils.cat_diagnose", level="INFO") as cm:
            parsed = parse_diagnoses_payload({
                "diagnoses": [{
                    "sentence_index": 0,
                    "quote": "界面上 按钮",
                    "category": "missing",
                    "severity": "medium",
                    "problem": "按钮名称缺失",
                    "revised": "",
                }]
            }, allowed_indexes={0})
        self.assertEqual(parsed, [])
        self.assertIn("reason=icon_placeholder", "\n".join(cm.output))

    def test_term_icon_placeholder_quote_is_kept(self):
        from app.utils.cat_diagnose import parse_diagnoses_payload

        parsed = parse_diagnoses_payload({
            "diagnoses": [{
                "sentence_index": 0,
                "quote": "界面上 按钮",
                "category": "term",
                "severity": "high",
                "problem": "非标准名",
                "revised": "界面上 Start 按钮",
            }]
        }, allowed_indexes={0})
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["category"], "term")
        self.assertEqual(parsed[0]["quote"], "界面上 按钮")


class CatDiagnoseRevisedFilterTest(unittest.TestCase):
    def test_empty_or_same_revised_is_dropped(self):
        from app.utils.cat_diagnose import parse_diagnoses_payload

        parsed = parse_diagnoses_payload({
            "diagnoses": [
                {
                    "sentence_index": 0,
                    "quote": "流道池",
                    "category": "term",
                    "severity": "high",
                    "problem": "非标准名",
                    "revised": "",
                    "rationale": "手册",
                },
                {
                    "sentence_index": 0,
                    "quote": "流道池",
                    "category": "term",
                    "severity": "high",
                    "problem": "非标准名",
                    "revised": "流道池",
                    "rationale": "手册",
                },
                {
                    "sentence_index": 0,
                    "quote": "流道池",
                    "category": "term",
                    "severity": "high",
                    "problem": "非标准名",
                    "revised": "flow cell",
                    "rationale": "手册",
                    "ruleable": True,
                    "rule_hint": "流道池",
                },
            ]
        }, allowed_indexes={0})
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["revised"], "flow cell")
        self.assertTrue(parsed[0]["ruleable"])
        self.assertEqual(parsed[0]["rule_hint"], "流道池")

    def test_hint_only_categories_keep_empty_or_identity_revised(self):
        from app.utils.cat_diagnose import parse_diagnoses_payload

        parsed = parse_diagnoses_payload({
            "diagnoses": [
                {
                    "sentence_index": 0,
                    "quote": "请勿关闭电源，关闭电源后再进行维护。",
                    "category": "logic",
                    "severity": "high",
                    "problem": "前后指令冲突",
                    "revised": "",
                    "rationale": "无法在不增补条件下给出忠实改写",
                },
                {
                    "sentence_index": 0,
                    "quote": "将其加入其中并观察结果。",
                    "category": "ambiguity",
                    "severity": "medium",
                    "problem": "指代不明",
                    "revised": "将其加入其中并观察结果。",
                    "rationale": "缺少明确对象",
                },
                {
                    "sentence_index": 0,
                    "quote": "将样本孵育后进行测序。",
                    "category": "missing",
                    "severity": "medium",
                    "problem": "缺少孵育条件",
                    "revised": "将样本在指定条件下孵育后进行测序。",
                    "rationale": "需要补参数，但当前只作提示",
                },
                {
                    "sentence_index": 0,
                    "quote": "流道池",
                    "category": "term",
                    "severity": "high",
                    "problem": "非标准名",
                    "revised": "",
                    "rationale": "手册",
                },
            ]
        }, allowed_indexes={0})
        self.assertEqual(len(parsed), 3)
        by_cat = {item["category"]: item for item in parsed}
        self.assertEqual(by_cat["logic"]["revised"], "")
        self.assertEqual(by_cat["ambiguity"]["revised"], "")
        self.assertEqual(by_cat["missing"]["revised"], "将样本在指定条件下孵育后进行测序。")
        self.assertNotIn("term", by_cat)


class CatDiagnoseBatchTest(unittest.TestCase):
    def test_sentences_are_split_into_batches_of_15(self):
        from app.utils import cat_diagnose

        calls = []

        async def fake_batch(
            sentences,
            terminology,
            sentence_guide,
            product_type,
            allowed_indexes=None,
            original_by_index=None,
        ):
            calls.append({
                "size": len(sentences),
                "allowed": set(allowed_indexes or []),
                "originals": set((original_by_index or {}).keys()),
            })
            return []

        items = [{"sentence_index": i, "text": f"句子{i}。"} for i in range(32)]
        with patch.dict(os.environ, {"AI_DIAGNOSE_ENABLED": "true", "AI_DIAGNOSE_BATCH_SIZE": "15"}, clear=False):
            with patch.object(cat_diagnose, "_diagnose_batch", side_effect=fake_batch):
                result = asyncio.run(cat_diagnose.open_diagnose_sentences(items, {}, "", ""))
        self.assertEqual(result, [])
        self.assertEqual([item["size"] for item in calls], [15, 15, 2])
        full_indexes = set(range(32))
        self.assertEqual(calls[0]["allowed"], full_indexes)
        self.assertEqual(calls[1]["allowed"], full_indexes)
        self.assertEqual(calls[2]["allowed"], full_indexes)
        self.assertEqual(calls[0]["originals"], full_indexes)


class CatDiagnoseCompactTextTest(unittest.TestCase):
    def test_compact_keeps_short_problem(self):
        from app.utils.cat_diagnose import compact_diagnose_text

        self.assertEqual(compact_diagnose_text("术语不规范", 36), "术语不规范")

    def test_compact_cuts_long_problem_to_first_clauses(self):
        from app.utils.cat_diagnose import compact_diagnose_text

        text = "“点击文本框”表述不完整，缺少点击后的操作对象或方式，且与前句3.5.2编号重复"
        compact = compact_diagnose_text(text, 36)
        self.assertLessEqual(len(compact), 36)
        self.assertIn("表述不完整", compact)
        self.assertNotIn("编号重复", compact)

    def test_duplicate_rationale_cleared_on_normalize(self):
        from app.utils.cat_diagnose import parse_diagnoses_payload

        parsed = parse_diagnoses_payload({
            "diagnoses": [{
                "sentence_index": 0,
                "quote": "至于常温解冻",
                "category": "spelling",
                "severity": "high",
                "problem": "“至于”为错别字，应为“置于”",
                "revised": "置于常温解冻",
                "rationale": "“至于”与“置于”字形相近但语义不同，此处应为“放置到”之意，属于错别字。",
            }],
        }, allowed_indexes={0})
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["problem"], "“至于”为错别字，应为“置于”")
        self.assertEqual(parsed[0]["rationale"], "")


class CatDiagnoseHintImportTest(unittest.TestCase):
    def test_hint_empty_revised_requires_replacement(self):
        from app.utils.cat_diagnose import hint_import_requires_replacement

        self.assertTrue(hint_import_requires_replacement("logic", ""))
        self.assertTrue(hint_import_requires_replacement("missing", "   "))
        self.assertTrue(hint_import_requires_replacement("ambiguity", None))
        self.assertFalse(hint_import_requires_replacement("logic", "关闭电源后再维护。"))
        self.assertFalse(hint_import_requires_replacement("term", ""))


if __name__ == "__main__":
    unittest.main()
