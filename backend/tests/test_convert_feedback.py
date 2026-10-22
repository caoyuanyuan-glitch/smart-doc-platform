import os
import tempfile
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
import sys

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.utils.convert_feedback import (
    apply_convert_feedback,
    apply_exact_patches,
    apply_hygiene,
    ensure_imesofttype,
    wrap_bare_li_and_entry,
)


SAMPLE_TOPIC = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">
<topic xmlns:cms="http://www.w3.org/ime/cms" xml:lang="zh-CN" id="topic-DTO41001" cms:keys="DTO41001" cms:title="安装" cms:number="DTO41001">
  <title id="title_DTO41001">安装</title>
  <body id="body_DTO41001">
    <ul>
      <li>第一步</li>
    </ul>
    <table>
      <tgroup cols="1">
        <tbody>
          <row><entry>单元格</entry></row>
        </tbody>
      </tgroup>
    </table>
  </body>
</topic>
"""


class HygieneTest(unittest.TestCase):
    def test_wraps_bare_li_and_entry(self):
        xml = wrap_bare_li_and_entry("<ul><li>第一步</li></ul><entry>单元格</entry>")
        self.assertIn("<li><p>第一步</p></li>", xml)
        self.assertIn("<entry><p>单元格</p></entry>", xml)

    def test_keeps_existing_p(self):
        xml = wrap_bare_li_and_entry("<li><p>已有</p></li>")
        self.assertEqual(xml, "<li><p>已有</p></li>")

    def test_adds_imesofttype_from_filename(self):
        xml = ensure_imesofttype(SAMPLE_TOPIC, "DTO41001.dita")
        self.assertIn('cms:imesofttype="sDitaTopic"', xml)

    def test_hygiene_keeps_well_formed_xml(self):
        xml = apply_hygiene(SAMPLE_TOPIC, "DTO41001.dita")
        self.assertIn("<li><p>第一步</p></li>", xml)
        self.assertIn('cms:imesofttype="sDitaTopic"', xml)


class PatchTest(unittest.TestCase):
    def test_applies_unique_fragment(self):
        xml, count = apply_exact_patches("<title>安装</title>", [{"find": "安装", "replace": "安装步骤"}])
        self.assertEqual(count, 1)
        self.assertEqual(xml, "<title>安装步骤</title>")

    def test_skips_non_unique_fragment(self):
        xml, count = apply_exact_patches("<p>安装</p><p>安装</p>", [{"find": "安装", "replace": "部署"}])
        self.assertEqual(count, 0)
        self.assertEqual(xml, "<p>安装</p><p>安装</p>")

    def test_skips_broken_xml(self):
        xml, count = apply_exact_patches("<title>安装</title>", [{"find": "</title>", "replace": ""}])
        self.assertEqual(count, 0)
        self.assertEqual(xml, "<title>安装</title>")


class ApplyFeedbackTest(unittest.TestCase):
    def test_hygiene_and_ai_patches(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "DTO41001.dita")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(SAMPLE_TOPIC)

            def fake_chat(messages, **kwargs):
                return '{"patches":[{"file":"DTO41001.dita","find":"<title id=\\"title_DTO41001\\">安装</title>","replace":"<title id=\\"title_DTO41001\\">安装步骤</title>"}]}'

            summary = apply_convert_feedback(tmp, "把安装改成安装步骤，并补 imesofttype", chat_fn=fake_chat)
            with open(path, encoding="utf-8") as handle:
                content = handle.read()
            self.assertIn("DTO41001.dita", summary["files_touched"])
            self.assertIn("<title id=\"title_DTO41001\">安装步骤</title>", content)
            self.assertIn('cms:imesofttype="sDitaTopic"', content)
            self.assertIn("<li><p>第一步</p></li>", content)

    def test_rejects_empty_feedback(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                apply_convert_feedback(tmp, "  ", chat_fn=lambda *args, **kwargs: "{}")


if __name__ == "__main__":
    unittest.main()
