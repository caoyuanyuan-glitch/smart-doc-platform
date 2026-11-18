import os
import tempfile
import unittest
import zipfile
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
    request_ai_patches,
    rewrite_zip_replacing_files,
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


class RequestAiPatchesTest(unittest.TestCase):
    def test_includes_screenshot_in_messages(self):
        calls = []

        def fake_chat(messages, **kwargs):
            calls.append(messages)
            return '{"patches":[]}'

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
            handle.write(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
            path = handle.name
        try:
            request_ai_patches({"DTO41001.dita": SAMPLE_TOPIC}, "缺 imesofttype", fake_chat, screenshot_path=path)
        finally:
            os.remove(path)
        self.assertEqual(len(calls), 1)
        content = calls[0][1]["content"]
        self.assertIsInstance(content, list)
        self.assertEqual(content[0]["type"], "text")
        self.assertEqual(content[1]["type"], "image_url")
        self.assertTrue(content[1]["image_url"]["url"].startswith("data:image/png;base64,"))

    def test_falls_back_to_text_when_vision_fails(self):
        calls = []

        def fake_chat(messages, **kwargs):
            calls.append(messages)
            content = messages[1]["content"]
            if isinstance(content, list):
                raise RuntimeError("vision unavailable")
            return '{"patches":[]}'

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
            handle.write(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
            path = handle.name
        try:
            patches = request_ai_patches(
                {"DTO41001.dita": SAMPLE_TOPIC}, "缺 imesofttype", fake_chat, screenshot_path=path
            )
        finally:
            os.remove(path)
        self.assertEqual(patches, [])
        self.assertEqual(len(calls), 2)
        self.assertIsInstance(calls[1][1]["content"], str)


class RewriteZipTest(unittest.TestCase):
    def test_keeps_unmodified_entry_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "src.zip")
            dest = os.path.join(tmp, "dest.zip")
            image_name = "image/中文图.svg"
            image_bytes = b"<svg id='keep'>ok</svg>"
            with zipfile.ZipFile(src, "w") as zf:
                info = zipfile.ZipInfo(image_name)
                info.flag_bits |= 0x800
                zf.writestr(info, image_bytes)
                zf.writestr("DTO41001.dita", SAMPLE_TOPIC.encode("utf-8"))
            rewrite_zip_replacing_files(src, dest, {"DTO41001.dita": SAMPLE_TOPIC.replace("安装", "安装步骤")})
            with zipfile.ZipFile(dest, "r") as zf:
                self.assertEqual(zf.read(image_name), image_bytes)
                self.assertIn("安装步骤", zf.read("DTO41001.dita").decode("utf-8"))
                kept = next(item for item in zf.infolist() if item.filename == image_name)
                self.assertTrue(kept.flag_bits & 0x800)


if __name__ == "__main__":
    unittest.main()
