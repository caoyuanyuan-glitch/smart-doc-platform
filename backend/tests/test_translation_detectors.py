import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from openpyxl import Workbook, load_workbook
from PIL import Image

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.api.translation import (  # noqa: E402
    _apply_memory_glossary,
    _append_memory_entry_to_delimited_file,
    _append_memory_entry_to_excel,
    _build_batch_separator,
    _build_memory_candidate_bundle,
    _build_memory_seed_file_path,
    _count_translatable_text_units,
    _collect_memory_candidates,
    _do_translate,
    _ensure_memory_bank_entry,
    _find_memory_glossary,
    _get_memory_file_candidates,
    _normalize_memory_file_ids,
    _get_memory_match_trace,
    _get_translate_task_status,
    _group_image_ocr_data,
    _detect_confirmation_button_blocks,
    _merge_image_ocr_blocks,
    _load_memory_file_entries,
    _looks_like_hallucination,
    _looks_like_invalid_translation,
    _match_memory_candidates,
    _mark_translation_canceled,
    _split_batched_translation_output,
    _thread_locals,
    _translate_tasks,
    _translate_tasks_lock,
    _sync_memory_file_to_seed,
    _translate_image,
)
from app.utils.runtime_paths import runtime_memory_seed_dir  # noqa: E402


class HallucinationTest(unittest.TestCase):
    def test_prompt_leak_detected(self):
        result = "译文如下：这是翻译好的内容"
        self.assertTrue(_looks_like_hallucination(result, "一些原文内容"))

    def test_clean_translation_not_detected(self):
        result = "The system loads the configuration on startup."
        self.assertFalse(_looks_like_hallucination(result, "系统启动时加载配置。"))


class InvalidTranslationTest(unittest.TestCase):
    def test_empty_result_invalid(self):
        self.assertTrue(_looks_like_invalid_translation("", "some source text here", "zh", "en"))

    def test_single_word_ack_invalid(self):
        self.assertTrue(_looks_like_invalid_translation("ok", "这是一段很长的需要翻译的内容，包含了多个句子。", "zh", "en"))

    def test_english_source_to_zh_keeps_no_cjk_invalid(self):
        self.assertTrue(_looks_like_invalid_translation("nothing chinese here at all", "Some english source text here.", "en", "zh"))

    def test_identifier_like_source_to_zh_without_cjk_allowed(self):
        self.assertFalse(_looks_like_invalid_translation("STUM-TT004", "STUM-TT004", "en", "zh"))

    def test_markdown_placeholder_to_zh_without_cjk_allowed(self):
        self.assertFalse(_looks_like_invalid_translation("%%LINK0%%", "%%LINK0%%", "en", "zh"))


class CancelFlowTest(unittest.TestCase):
    def test_mark_canceled_updates_status(self):
        doc_id = 999999
        with _translate_tasks_lock:
            _translate_tasks[doc_id] = {"status": "processing"}
        _mark_translation_canceled(doc_id, message="用户取消")
        self.assertEqual(_get_translate_task_status(doc_id), "canceled")
        with _translate_tasks_lock:
            _translate_tasks.pop(doc_id, None)


class ImageTranslationTest(unittest.TestCase):
    def test_groups_ocr_words_into_ordered_lines(self):
        blocks = _group_image_ocr_data({
            "text": ["Open", "Settings", "Save"],
            "conf": [96, 93, 91],
            "left": [10, 50, 10],
            "top": [20, 20, 60],
            "width": [35, 55, 35],
            "height": [16, 16, 16],
            "block_num": [1, 1, 1],
            "par_num": [1, 1, 1],
            "line_num": [1, 1, 2],
        })

        self.assertEqual([block["text"] for block in blocks], ["Open Settings", "Save"])
        self.assertEqual(blocks[0]["left"], 10)
        self.assertEqual(blocks[0]["width"], 95)

    def test_joins_cjk_words_without_inserting_spaces(self):
        blocks = _group_image_ocr_data({
            "text": ["设置", "页面"],
            "conf": [96, 93],
            "left": [10, 50],
            "top": [20, 20],
            "width": [35, 35],
            "height": [16, 16],
            "block_num": [1, 1],
            "par_num": [1, 1],
            "line_num": [1, 1],
        })

        self.assertEqual(blocks[0]["text"], "设置页面")

    def test_discards_low_confidence_ocr_words(self):
        blocks = _group_image_ocr_data({
            "text": ["garbage", "Valid"],
            "conf": [12, 92],
            "left": [10, 10],
            "top": [20, 60],
            "width": [50, 40],
            "height": [16, 16],
            "block_num": [1, 1],
            "par_num": [1, 1],
            "line_num": [1, 2],
        })

        self.assertEqual([block["text"] for block in blocks], ["Valid"])

    def test_discards_single_character_ocr_noise(self):
        blocks = _group_image_ocr_data({
            "text": ["©", "设置"],
            "conf": [96, 93],
            "left": [10, 10],
            "top": [20, 60],
            "width": [16, 35],
            "height": [16, 16],
            "block_num": [1, 1],
            "par_num": [1, 1],
            "line_num": [1, 2],
        })

        self.assertEqual([block["text"] for block in blocks], ["设置"])

    def test_merges_complementary_ocr_layout_results(self):
        merged = _merge_image_ocr_blocks([
            [{"text": "确认测序对话框", "left": 140, "top": 220, "width": 130, "height": 18, "confidence": 95}],
            [{"text": "是否要测序？", "left": 145, "top": 100, "width": 110, "height": 20, "confidence": 86}],
        ])

        self.assertEqual([block["text"] for block in merged], ["是否要测序？", "确认测序对话框"])

    def test_prefers_higher_confidence_duplicate_ocr_block(self):
        merged = _merge_image_ocr_blocks([
            [{"text": "确认测序", "left": 140, "top": 220, "width": 100, "height": 18, "confidence": 60}],
            [{"text": "确认测序", "left": 142, "top": 220, "width": 100, "height": 18, "confidence": 93}],
        ])

        self.assertEqual(merged, [{"text": "确认测序", "left": 142, "top": 220, "width": 100, "height": 18}])

    def test_recovers_confirmation_button_labels_from_paired_borders(self):
        image = Image.new("L", (400, 240), "white")
        for x in range(80, 180):
            image.putpixel((x, 170), 0)
        for x in range(200, 300):
            image.putpixel((x, 170), 0)
        for x in range(80, 180):
            image.putpixel((x, 190), 0)
        for x in range(200, 300):
            image.putpixel((x, 190), 0)

        blocks = _detect_confirmation_button_blocks(image, [{"text": "是否继续操作？", "left": 140, "top": 90, "width": 100, "height": 20}])

        self.assertEqual([block["text"] for block in blocks], ["否", "是"])
        self.assertEqual([block["left"] for block in blocks], [82, 202])
        self.assertEqual([block["draw_background"] for block in blocks], [True, True])
        self.assertEqual([block["height"] for block in blocks], [16, 16])
        self.assertTrue(all(block["font_size"] <= block["height"] for block in blocks))
        self.assertEqual(blocks[0]["font_size"], blocks[1]["font_size"])

    def test_recovers_english_confirmation_button_labels_from_paired_borders(self):
        image = Image.new("L", (400, 240), "white")
        for x in range(80, 180):
            image.putpixel((x, 170), 0)
            image.putpixel((x, 190), 0)
        for x in range(200, 300):
            image.putpixel((x, 170), 0)
            image.putpixel((x, 190), 0)

        blocks = _detect_confirmation_button_blocks(image, [{"text": "Proceed with sequencing ?", "left": 120, "top": 90, "width": 140, "height": 20}])

        self.assertEqual([block["text"] for block in blocks], ["No", "Yes"])
        self.assertEqual(blocks[0]["font_size"], blocks[1]["font_size"])

    def test_button_blocks_override_tiny_duplicate_ocr_labels(self):
        merged = _merge_image_ocr_blocks([
            [{"text": "Yes", "left": 214, "top": 141, "width": 13, "height": 5, "confidence": 88}],
            [{"text": "Yes", "left": 203, "top": 156, "width": 112, "height": 22, "confidence": 999, "font_size": 14, "draw_background": True, "center_text": True}],
        ])

        self.assertEqual(merged, [{"text": "Yes", "left": 203, "top": 156, "width": 112, "height": 22, "font_size": 14, "draw_background": True, "center_text": True}])

    def test_translates_image_to_same_image_format(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_path = Path(tmp_dir) / "source.png"
            Image.new("RGB", (180, 80), "white").save(source_path)
            blocks = [{"text": "Open settings", "left": 10, "top": 10, "width": 120, "height": 24}]

            with patch("app.api.translation._extract_image_ocr_blocks", return_value=(Image.open(source_path), blocks)), \
                 patch("app.api.translation._translate_text_items", return_value=["Open configuration"]):
                translated, original, output = _translate_image(str(source_path), "ai", "kimi", "en", "en", db=None)

            self.assertEqual(original, ["Open settings"])
            self.assertEqual(output, ["Open configuration"])
            with Image.open(__import__("io").BytesIO(translated)) as image:
                self.assertEqual(image.format, "PNG")


class HybridMemoryFallbackTest(unittest.TestCase):
    def tearDown(self):
        for attr in ["memory_bank", "memory_file_id", "memory_file_ids", "translation_usage_stats", "memory_candidate_cache"]:
            if hasattr(_thread_locals, attr):
                delattr(_thread_locals, attr)

    def test_hybrid_falls_back_to_partial_memory_when_ai_unavailable(self):
        bundle = _build_memory_candidate_bundle([
            {"source_text": "settings", "translated_text": "设置"}
        ])

        with patch("app.api.translation._get_memory_candidate_bundle", return_value=bundle), \
             patch("app.api.translation.translate_with_ai", side_effect=HTTPException(status_code=500, detail="AI翻译引擎不可用")):
            translated = _do_translate("Open settings page", "hybrid", "kimi", "en", "zh", db=None)

        self.assertEqual(translated, "Open 设置 page")

    def test_hybrid_multi_segment_falls_back_to_memory_when_ai_unavailable(self):
        bundle = _build_memory_candidate_bundle([
            {"source_text": "settings", "translated_text": "设置"}
        ])

        with patch("app.api.translation._get_memory_candidate_bundle", return_value=bundle), \
             patch("app.api.translation.translate_with_ai", side_effect=HTTPException(status_code=500, detail="AI翻译引擎不可用")):
            translated = _do_translate("Open settings page.\nClose settings page.", "hybrid", "kimi", "en", "zh", db=None)

        self.assertEqual(translated, "Open 设置 page.\nClose 设置 page.")


class EnsureMemoryBankEntryTest(unittest.TestCase):
    def test_creates_new_entry_when_missing(self):
        db = unittest.mock.MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        entry, created = _ensure_memory_bank_entry(db, "hello", "你好", "en", "zh")

        self.assertTrue(created)
        self.assertEqual(entry.source_text, "hello")
        self.assertEqual(entry.translated_text, "你好")
        db.add.assert_called_once_with(entry)

    def test_skips_duplicate_entry(self):
        db = unittest.mock.MagicMock()
        existing = unittest.mock.MagicMock()
        db.query.return_value.filter.return_value.first.return_value = existing

        entry, created = _ensure_memory_bank_entry(db, "hello", "你好", "en", "zh")

        self.assertFalse(created)
        self.assertIs(entry, existing)
        db.add.assert_not_called()


class MemorySeedSyncTest(unittest.TestCase):
    def test_build_seed_path_preserves_folder_structure(self):
        root = SimpleNamespace(name="资源库", parent=None)
        child = SimpleNamespace(name="记忆库", parent=root)
        memory_file = SimpleNamespace(file_path="/tmp/source.xlsx", name="AI翻译语料写入Excel.xlsx", folder=child)

        seed_path = _build_memory_seed_file_path(memory_file, seed_root=Path("/tmp/seed-root"))

        self.assertEqual(seed_path, Path("/tmp/seed-root/资源库/记忆库/AI翻译语料写入Excel.xlsx"))

    def test_sync_memory_file_to_seed_copies_content(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            source_path = tmp_path / "source.xlsx"
            source_path.write_bytes(b"seed-content")

            root = SimpleNamespace(name="资源库", parent=None)
            child = SimpleNamespace(name="记忆库", parent=root)
            memory_file = SimpleNamespace(file_path=str(source_path), name="AI翻译语料写入Excel.xlsx", folder=child)

            seed_file_path = _sync_memory_file_to_seed(memory_file, seed_root=tmp_path / "seed")

            self.assertTrue(seed_file_path.exists())
            self.assertEqual(seed_file_path.read_bytes(), b"seed-content")
            self.assertEqual(seed_file_path, tmp_path / "seed" / "资源库" / "记忆库" / "AI翻译语料写入Excel.xlsx")

    def test_runtime_memory_seed_dir_is_shared_location(self):
        shared_dir = runtime_memory_seed_dir()
        self.assertIn(".smart-doc-platform", str(shared_dir))


class MemoryNormalizationTest(unittest.TestCase):
    def tearDown(self):
        if hasattr(_thread_locals, "memory_match_trace"):
            delattr(_thread_locals, "memory_match_trace")

    def test_match_ignores_case_spaces_and_special_characters(self):
        bundle = _build_memory_candidate_bundle([
            {"source_text": "Open Settings Page", "translated_text": "打开设置页面"}
        ])

        matched = _match_memory_candidates("open_settings-(page)", bundle)

        self.assertEqual(matched, "打开设置页面")
        self.assertEqual(_get_memory_match_trace()[-1]["reason"], "compact_exact")

    def test_match_preserves_symbols_when_candidate_is_embedded(self):
        bundle = _build_memory_candidate_bundle([
            {"source_text": "DNBSEQ T7 Gene Sequencer", "translated_text": "DNBSEQ T7 基因测序仪"}
        ])

        matched = _match_memory_candidates("[DNBSEQ-T7] Gene_Sequencer", bundle)

        self.assertEqual(matched, "DNBSEQ T7 基因测序仪")

    def test_match_hits_embedded_phrase_inside_longer_sentence(self):
        bundle = _build_memory_candidate_bundle([
            {"source_text": "open settings page", "translated_text": "打开设置页面"}
        ])

        matched = _match_memory_candidates("Please open - settings_page now.", bundle)

        self.assertEqual(matched, "Please 打开设置页面 now.")

    def test_match_prefers_longer_embedded_phrase(self):
        bundle = _build_memory_candidate_bundle([
            {"source_text": "settings", "translated_text": "设置"},
            {"source_text": "open settings page", "translated_text": "打开设置页面"}
        ])

        matched = _match_memory_candidates("Please open settings page now", bundle)

        self.assertEqual(matched, "Please 打开设置页面 now")

    def test_glossary_prefers_longer_phrases_and_replaces_multiple_terms(self):
        glossary = _find_memory_glossary(
            "Please open settings page and close settings page.",
            [
                {"source_text": "settings", "translated_text": "设置"},
                {"source_text": "open settings page", "translated_text": "打开设置页面"},
                {"source_text": "close settings page", "translated_text": "关闭设置页面"},
            ],
        )

        translated, replaced = _apply_memory_glossary(
            "Please open_settings-page and close settings page.",
            glossary,
        )

        self.assertTrue(replaced)
        self.assertEqual(translated, "Please 打开设置页面 and 关闭设置页面.")

    def test_match_prefers_more_specific_candidate_among_similar_terms(self):
        bundle = _build_memory_candidate_bundle([
            {"source_text": "gene sequencer", "translated_text": "测序仪"},
            {"source_text": "DNBSEQ T7 gene sequencer", "translated_text": "DNBSEQ T7 基因测序仪"},
        ])

        matched = _match_memory_candidates("The DNBSEQ-T7 Gene_Sequencer is ready.", bundle)

        self.assertEqual(matched, "The DNBSEQ T7 基因测序仪 is ready.")
        trace = _get_memory_match_trace()[-1]
        self.assertEqual(trace["reason"], "token_subsequence")
        self.assertEqual(trace["candidate_text"], "DNBSEQ T7 gene sequencer")

    def test_match_ignores_locale_suffix_metadata(self):
        bundle = _build_memory_candidate_bundle([
            {
                "source_text": "DNBSEQ-T7+RS Genetic Sequencer System Guide_Chinese_RUO_WH",
                "translated_text": "DNBSEQ-T7+RS 基因测序仪系统指南_中文_RUO_WH",
            }
        ])

        matched = _match_memory_candidates(
            "DNBSEQ-T7+RS Genetic Sequencer System Guide_English_RUO_WH",
            bundle,
        )

        self.assertEqual(matched, "DNBSEQ-T7+RS 基因测序仪系统指南_中文_RUO_WH")
        self.assertEqual(_get_memory_match_trace()[-1]["reason"], "metadata_exact")

    def test_match_ignores_version_metadata_variants(self):
        bundle = _build_memory_candidate_bundle([
            {
                "source_text": "Mammoth COOLING Control Board V3.0.0",
                "translated_text": "Mammoth 冷却控制板 V3.0.0",
            }
        ])

        matched = _match_memory_candidates("Mammoth COOLING Control Board V3.0.0.0", bundle)

        self.assertEqual(matched, "Mammoth 冷却控制板 V3.0.0")
        self.assertEqual(_get_memory_match_trace()[-1]["reason"], "metadata_exact")


class TranslationStatisticsTest(unittest.TestCase):
    def test_count_translatable_text_units_skips_codes_versions_and_locale_tags(self):
        count = _count_translatable_text_units(
            "DNBSEQ-T7+RS Genetic Sequencer System Guide_English_RUO_WH V3.0.0"
        )

        self.assertEqual(count, 4)


class MemoryFileSelectionTest(unittest.TestCase):
    def test_normalize_memory_file_ids_merges_and_deduplicates(self):
        self.assertEqual(_normalize_memory_file_ids(memory_file_ids=[3, "2", 3, 0, None], memory_file_id=2), [3, 2])

    def test_collect_memory_candidates_merges_multiple_files_in_order(self):
        db = unittest.mock.MagicMock()
        db.query.return_value.filter.return_value.all.return_value = []

        with patch("app.api.translation._get_memory_file_candidates") as get_candidates:
            get_candidates.side_effect = [
                [
                    {"source_text": "Alpha", "translated_text": "阿尔法"},
                    {"source_text": "Beta", "translated_text": "贝塔"},
                ],
                [
                    {"source_text": "Beta", "translated_text": "贝塔"},
                    {"source_text": "Gamma", "translated_text": "伽马"},
                ],
            ]

            candidates = _collect_memory_candidates(db, "en", "zh", memory_file_ids=[11, 12])

        self.assertEqual(
            candidates,
            [
                {"source_text": "Alpha", "translated_text": "阿尔法"},
                {"source_text": "Beta", "translated_text": "贝塔"},
                {"source_text": "Gamma", "translated_text": "伽马"},
            ],
        )


class BatchedTranslationHelpersTest(unittest.TestCase):
    def test_build_batch_separator_avoids_existing_marker(self):
        separator = _build_batch_separator(["alpha [[MC_DOCSEG]] beta", "gamma"])

        self.assertNotEqual(separator.strip(), "[[MC_DOCSEG]]")
        self.assertNotIn(separator.strip(), "alpha [[MC_DOCSEG]] beta")

    def test_split_batched_translation_output_uses_exact_separator(self):
        separator = _build_batch_separator(["第一段", "第二段"])

        parts = _split_batched_translation_output(
            f"译文一{separator}译文二",
            separator,
            2,
            "batch_split_error",
        )

        self.assertEqual(parts, ["译文一", "译文二"])

    def test_split_batched_translation_output_rejects_missing_separator(self):
        with self.assertRaises(ValueError):
            _split_batched_translation_output("only one part", "\n[[MC_DOCSEG]]\n", 2, "batch_split_error")


class MemoryFileWriteTest(unittest.TestCase):
    def test_append_csv_memory_entry_respects_language_headers(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "memory.csv"
            csv_path.write_bytes("zh-CN,en-US\n已有译文,Existing Source\n".encode("gb18030"))
            memory_file = SimpleNamespace(file_path=str(csv_path), file_type="csv")

            _append_memory_entry_to_delimited_file(
                memory_file,
                source_text="New Source",
                translated_text="新增译文",
                source_lang="en",
                target_lang="zh",
            )

            entries = _load_memory_file_entries(str(csv_path), "csv")
            self.assertTrue(any(item.get("bilingual_values", {}).get("en") == "New Source" and item.get("bilingual_values", {}).get("zh") == "新增译文" for item in entries))

            db = unittest.mock.MagicMock()
            db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
                id=1,
                file_path=str(csv_path),
                file_type="csv",
                updated_at=None,
            )
            candidates = _get_memory_file_candidates(db, 1, "en", "zh")
            self.assertTrue(any(item["source_text"] == "New Source" and item["translated_text"] == "新增译文" for item in candidates))

            content = csv_path.read_bytes().decode("gb18030")
            self.assertIn("新增译文,New Source", content)

    def test_append_excel_memory_entry_respects_language_headers(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            xlsx_path = Path(tmpdir) / "memory.xlsx"
            wb = Workbook()
            ws = wb.active
            ws.cell(row=1, column=1).value = "zh-CN"
            ws.cell(row=1, column=2).value = "en-US"
            wb.save(xlsx_path)
            wb.close()

            memory_file = SimpleNamespace(file_path=str(xlsx_path), file_type="xlsx")
            _append_memory_entry_to_excel(
                memory_file,
                source_text="New Source",
                translated_text="新增译文",
                source_lang="en",
                target_lang="zh",
            )

            workbook = load_workbook(xlsx_path, read_only=True, data_only=True)
            worksheet = workbook.active
            self.assertEqual(worksheet.cell(row=2, column=1).value, "新增译文")
            self.assertEqual(worksheet.cell(row=2, column=2).value, "New Source")
            workbook.close()

if __name__ == "__main__":
    unittest.main()
