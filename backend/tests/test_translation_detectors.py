import sys
import threading
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.api.translation import (  # noqa: E402
    TranslationCancelled,
    _find_chunk_cut,
    _get_translate_task_status,
    _looks_like_hallucination,
    _looks_like_invalid_translation,
    _looks_like_repetitive_fill,
    _looks_like_untranslated,
    _mark_translation_canceled,
    _split_text_for_ai_chunks,
    _translate_tasks,
    _translate_tasks_lock,
)


class SplitChunkTest(unittest.TestCase):
    def test_short_text_stays_single_chunk(self):
        chunks = _split_text_for_ai_chunks("hello world", max_chars=7000)
        self.assertEqual(chunks, ["hello world"])

    def test_empty_text_returns_empty_list(self):
        self.assertEqual(_split_text_for_ai_chunks(""), [])

    def test_long_text_is_split_into_chunks_within_limit(self):
        text = ("第一段。第二段。第三段。" * 2000) + ("\n" * 20)
        chunks = _split_text_for_ai_chunks(text, max_chars=7000)
        self.assertGreater(len(chunks), 1)
        self.assertEqual("".join(chunks), text)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 7000)

    def test_unbroken_long_run_hard_splits(self):
        text = "x" * 20000
        chunks = _split_text_for_ai_chunks(text, max_chars=7000)
        self.assertGreater(len(chunks), 1)
        self.assertEqual("".join(chunks), text)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 7000)

    def test_chunk_cut_prefers_sentence_boundary(self):
        text = "abc。" + "d" * 8000
        cut = _find_chunk_cut(text, 7000)
        self.assertEqual(text[:cut].rstrip("d").endswith("。"), True)


class RepetitiveFillTest(unittest.TestCase):
    def test_repetitive_fill_detected(self):
        original = "这是一个需要翻译的源文本句子。这是一个需要翻译的源文本句子。这是一个需要翻译的源文本句子。"
        result = "这是一条被模型重复填充的译文。" * 120
        self.assertTrue(_looks_like_repetitive_fill(result, original))

    def test_normal_translation_not_detected(self):
        original = "系统启动时加载配置。" * 4
        result = "The system loads the configuration on startup. The service binds on port 8080. The log rotates daily. The worker retries on failure."
        self.assertFalse(_looks_like_repetitive_fill(result, original))


class HallucinationTest(unittest.TestCase):
    def test_prompt_leak_detected(self):
        result = "译文如下：这是翻译好的内容"
        self.assertTrue(_looks_like_hallucination(result, "一些原文内容"))

    def test_clean_translation_not_detected(self):
        result = "The system loads the configuration on startup."
        self.assertFalse(_looks_like_hallucination(result, "系统启动时加载配置。"))


class UntranslatedTest(unittest.TestCase):
    def test_exact_echo_detected(self):
        self.assertTrue(_looks_like_untranslated("hello world", "hello world", "en", "zh"))

    def test_near_duplicate_detected(self):
        original = "系统启动时加载配置文件并初始化日志模块。"
        result = "系统启动时加载配置文件并初始化日志模块。 "
        self.assertTrue(_looks_like_untranslated(result, original, "zh", "en"))

    def test_real_translation_not_detected(self):
        self.assertFalse(_looks_like_untranslated("The system loads the config.", "系统启动时加载配置。", "zh", "en"))

    def test_same_source_and_target_skipped(self):
        self.assertFalse(_looks_like_untranslated("hello", "hello", "en", "en"))


class InvalidTranslationTest(unittest.TestCase):
    def test_empty_result_invalid(self):
        self.assertTrue(_looks_like_invalid_translation("", "some source text here", "zh", "en"))

    def test_single_word_ack_invalid(self):
        self.assertTrue(_looks_like_invalid_translation("ok", "这是一段很长的需要翻译的内容，包含了多个句子。", "zh", "en"))

    def test_english_source_to_zh_keeps_no_cjk_invalid(self):
        self.assertTrue(_looks_like_invalid_translation("nothing chinese here at all", "Some english source text here.", "en", "zh"))


class CancelFlowTest(unittest.TestCase):
    def test_mark_canceled_updates_status(self):
        doc_id = 999999
        with _translate_tasks_lock:
            _translate_tasks[doc_id] = {"status": "processing"}
        _mark_translation_canceled(doc_id, message="用户取消")
        self.assertEqual(_get_translate_task_status(doc_id), "canceled")
        with _translate_tasks_lock:
            _translate_tasks.pop(doc_id, None)


class SemaphoreTest(unittest.TestCase):
    def test_semaphore_limits_concurrency(self):
        from app.api.translation import _translate_semaphore

        acquired = []
        releases = []

        def worker(i):
            if _translate_semaphore.acquire(blocking=False):
                acquired.append(i)
                releases.append(i)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for i in releases:
            _translate_semaphore.release()

        self.assertEqual(len(acquired), len(releases))
        self.assertLessEqual(len(acquired), 4)
        self.assertGreaterEqual(len(acquired), 1)


if __name__ == "__main__":
    unittest.main()
