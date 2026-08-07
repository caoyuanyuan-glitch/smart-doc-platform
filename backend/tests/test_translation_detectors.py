import sys
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.api.translation import (  # noqa: E402
    _get_translate_task_status,
    _looks_like_hallucination,
    _looks_like_invalid_translation,
    _mark_translation_canceled,
    _translate_tasks,
    _translate_tasks_lock,
)


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
if __name__ == "__main__":
    unittest.main()
