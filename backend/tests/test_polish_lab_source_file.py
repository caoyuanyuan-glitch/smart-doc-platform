import sys
import unittest
from pathlib import Path

from fastapi import HTTPException


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.api.polish_lab import _ensure_word_source_filename  # noqa: E402


class PolishLabSourceFileTest(unittest.TestCase):
    def test_docx_is_allowed(self):
        self.assertEqual(_ensure_word_source_filename("操作手册.docx"), "docx")

    def test_txt_is_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            _ensure_word_source_filename("操作手册.txt")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Word", ctx.exception.detail)

    def test_markdown_is_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            _ensure_word_source_filename("操作手册.md")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Word", ctx.exception.detail)

    def test_legacy_doc_asks_for_docx(self):
        with self.assertRaises(HTTPException) as ctx:
            _ensure_word_source_filename("操作手册.doc")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn(".docx", ctx.exception.detail)


if __name__ == "__main__":
    unittest.main()
