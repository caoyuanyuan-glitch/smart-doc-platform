import os
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.utils.convert_verify import verify_output_dir
from app.api.convert import _load_source_content


TOPIC_XML = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">
<topic id="DTO41001">
  <title>安装</title>
  <body><p>第一步</p></body>
</topic>
"""

EMPTY_BODY_XML = """<?xml version="1.0" encoding="UTF-8"?>
<topic id="DTO41002">
  <title>空章节</title>
  <body></body>
</topic>
"""

MAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<bookmap>
  <chapter href="DTO41001.dita" navtitle="安装"/>
</bookmap>
"""


class VerifyOutputDirTest(unittest.TestCase):
    def test_missing_dir_fails(self):
        overall, checks = verify_output_dir("/tmp/convert-verify-missing-dir", "dita")
        self.assertEqual(overall, "failed")
        self.assertEqual(checks[0]["status"], "failed")

    def test_valid_package_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "DTO41001.dita").write_text(TOPIC_XML, encoding="utf-8")
            Path(tmp, "book.ditamap").write_text(MAP_XML, encoding="utf-8")
            overall, checks = verify_output_dir(tmp, "dita")
        self.assertEqual(overall, "passed")
        names = {item["name"]: item["status"] for item in checks}
        self.assertEqual(names["结构完整性"], "passed")
        self.assertEqual(names["引用可达"], "passed")
        self.assertEqual(names["空正文"], "passed")

    def test_missing_href_is_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "book.ditamap").write_text(MAP_XML, encoding="utf-8")
            overall, checks = verify_output_dir(tmp, "dita")
        self.assertEqual(overall, "warning")
        href_check = next(item for item in checks if item["name"] == "引用可达")
        self.assertEqual(href_check["status"], "failed")

    def test_empty_body_is_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "DTO41002.dita").write_text(EMPTY_BODY_XML, encoding="utf-8")
            overall, checks = verify_output_dir(tmp, "dita")
        self.assertEqual(overall, "warning")
        body_check = next(item for item in checks if item["name"] == "空正文")
        self.assertEqual(body_check["status"], "warning")

    def test_markdown_counts_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "index.md").write_text("# hi\n", encoding="utf-8")
            overall, checks = verify_output_dir(tmp, "markdown")
        self.assertEqual(overall, "passed")
        self.assertIn("1 个 Markdown", checks[0]["detail"])

    def test_csv_skips_xml(self):
        overall, checks = verify_output_dir("/unused", "csv")
        self.assertEqual(overall, "passed")
        self.assertEqual(checks[0]["name"], "结构完整性")


class LoadSourceContentTest(unittest.TestCase):
    def test_keeps_existing_content(self):
        self.assertEqual(_load_source_content("md", "/no/such/file.md", "# Title\n"), "# Title\n")

    def test_reads_markdown_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "doc.md")
            Path(path).write_text("# 手册\n\n正文\n", encoding="utf-8")
            text = _load_source_content("md", path, "")
        self.assertIn("手册", text)
        self.assertIn("正文", text)


if __name__ == "__main__":
    unittest.main()
