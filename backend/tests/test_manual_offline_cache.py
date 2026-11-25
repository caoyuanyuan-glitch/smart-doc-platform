import unittest
from unittest.mock import patch

from app.api import manual_search
from app.utils.official_manual import cache_file_id


class ManualOfflineCacheTest(unittest.TestCase):
    def _item(self, cached=True):
        return {
            "official_id": 42,
            "create_time": "2026-01-01",
            "files": "https://global-mgitech.com/files/manual.pdf",
            "_cached": cached,
        }

    def test_cached_index_without_local_pdf_is_unavailable(self):
        with patch.object(manual_search, "UPLOAD_SESSIONS", {}), patch.object(
            manual_search, "has_cached_en_pdf", return_value=False
        ):
            self.assertTrue(manual_search._offline_pdf_unavailable([self._item()], "user"))

    def test_cached_index_with_local_pdf_is_available(self):
        with patch.object(manual_search, "UPLOAD_SESSIONS", {}), patch.object(
            manual_search, "has_cached_en_pdf", return_value=True
        ):
            self.assertFalse(manual_search._offline_pdf_unavailable([self._item()], "user"))

    def test_parsed_upload_skips_offline_check(self):
        item = self._item()
        uploads = {"user": {cache_file_id(item): {"pages": [{"page_num": 1, "text": "x"}]}}}
        with patch.object(manual_search, "UPLOAD_SESSIONS", uploads), patch.object(
            manual_search, "has_cached_en_pdf", return_value=False
        ):
            self.assertFalse(manual_search._offline_pdf_unavailable([item], "user"))

    def test_online_item_does_not_trigger_offline_notice(self):
        with patch.object(manual_search, "UPLOAD_SESSIONS", {}), patch.object(
            manual_search, "has_cached_en_pdf", return_value=False
        ):
            self.assertFalse(
                manual_search._offline_pdf_unavailable([self._item(cached=False)], "user")
            )


if __name__ == "__main__":
    unittest.main()
