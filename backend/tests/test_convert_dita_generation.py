import sys
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.api.convert import (  # noqa: E402
    _append_root_container_xml,
    _content_to_dita_xml,
    _generated_topic_code,
    _copy_docx_media_to_output,
    _download_images_for_output,
    _topic_placeholder,
)

TOOLS_ROOT = BACKEND_ROOT / "tools"
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from verify_word_to_dita_package import _parse_dita_package  # noqa: E402


class GeneratedTopicCodeTest(unittest.TestCase):
    def test_cover_uses_ctt_prefix(self):
        self.assertTrue(_generated_topic_code(1, "cover").startswith("CTT"))

    def test_root_chapter_uses_cto_prefix(self):
        self.assertTrue(_generated_topic_code(2, "chapter").startswith("CTO"))

    def test_concept_uses_dtc_prefix(self):
        self.assertTrue(_generated_topic_code(3, "concept").startswith("DTC"))

    def test_task_uses_dto_prefix(self):
        self.assertTrue(_generated_topic_code(4, "task").startswith("DTO"))


class TopicPlaceholderTest(unittest.TestCase):
    def test_placeholder_uses_filename_stem(self):
        self.assertEqual(_topic_placeholder({"filename": "DTC041002.dita"}), "DTC041002")


class ContentGenerationTest(unittest.TestCase):
    def test_chapter_topics_use_concept_shell(self):
        xml = _content_to_dita_xml(
            "测序",
            "第一段\n- 条目",
            "concept",
            "CTO041001",
            "zh-CN",
            topic_kind="chapter",
        )
        self.assertIn("<concept ", xml)
        self.assertIn("<conbody ", xml)
        self.assertIn('cms:imesofttype="chapterTopic"', xml)
        self.assertIn('id="concept-CTO041001"', xml)

    def test_task_topics_use_topic_shell(self):
        xml = _content_to_dita_xml(
            "进行磁珠分选",
            "1. 步骤一",
            "task",
            "DTO041002",
            "zh-CN",
            topic_kind="task",
        )
        self.assertIn("<topic ", xml)
        self.assertIn("<body ", xml)
        self.assertIn('cms:imesofttype="sDitaTopic"', xml)
        self.assertIn('id="topic-DTO041002"', xml)

    def test_cover_topics_use_cover_metadata(self):
        xml = _content_to_dita_xml(
            "封面CN",
            "编号",
            "concept",
            "CTT041003",
            "zh-CN",
            topic_kind="cover",
        )
        self.assertIn('outputclass="cover A4"', xml)
        self.assertIn('cms:imesofttype="sCoverTopic"', xml)

    def test_title_quotes_are_escaped_in_attributes(self):
        xml = _content_to_dita_xml(
            '末端修复产物纯化和加 "A" 尾',
            '正文',
            'concept',
            'DTC041206',
            'zh-CN',
            topic_kind='concept',
        )
        self.assertIn('cms:title="末端修复产物纯化和加 &quot;A&quot; 尾"', xml)

    def test_warning_paragraphs_become_note(self):
        xml = _content_to_dita_xml(
            "连接产物纯化",
            "小心吸取上清并丢弃。\n请勿触碰磁珠。",
            "concept",
            "DTC041200",
            "zh-CN",
            topic_kind="concept",
        )
        self.assertIn('<note type="warning"><p>吸取上清并丢弃。</p></note>', xml)
        self.assertIn('<note type="warning"><p>触碰磁珠。</p></note>', xml)

    def test_table_heading_becomes_table_title(self):
        xml = _content_to_dita_xml(
            "表 30 Fe (II) 稀释液配置",
            "表 30 Fe (II) 稀释液配置\n| 组分 | 体积 |\n| :--- | :--- |\n| Fe (II) Solution | 1 μL |",
            "task",
            "DTO041201",
            "zh-CN",
            topic_kind="task",
        )
        self.assertIn('<table>\n          <title>表 30 Fe (II) 稀释液配置</title>', xml)

    def test_adjacent_tables_keep_their_own_titles(self):
        xml = _content_to_dita_xml(
            "连续表格",
            "表 11 试剂准备\n| 试剂名称 | 要求 |\n| :--- | :--- |\n| TE Buffer | 室温暂存 |\n\n表 12 样本准备\n| 样本名称 | 用途 |\n| :--- | :--- |\n| DNA | 待检测 |",
            "concept",
            "DTC041205",
            "zh-CN",
            topic_kind="concept",
        )
        self.assertIn('<title>表 11 试剂准备</title>', xml)
        self.assertIn('<title>表 12 样本准备</title>', xml)

    def test_markdown_lists_map_to_ol_and_ul(self):
        xml = _content_to_dita_xml(
            "准备",
            "1. 第一步\n2. 第二步\n\n- 提示一\n- 提示二",
            "task",
            "DTO041202",
            "zh-CN",
            topic_kind="task",
        )
        self.assertIn('<ol>', xml)
        self.assertIn('<ul>', xml)

    def test_figure_caption_wraps_pending_image(self):
        xml = _content_to_dita_xml(
            "图片示例",
            "![docx_image_001.png](image/docx_image_001.png)\n图 1 示例图片",
            "concept",
            "DTC041203",
            "zh-CN",
            topic_kind="concept",
        )
        self.assertIn('<fig><title>图 1 示例图片</title><image href="image/docx_image_001.png" placement="break"><alt>docx_image_001.png</alt></image></fig>', xml)

    def test_note_icon_image_is_skipped_when_adjacent_to_warning_text(self):
        xml = _content_to_dita_xml(
            "连接产物纯化",
            "- 添加试剂、转移上清时请勿触碰、吸取磁珠。\n![docx_image_002.png](image/docx_image_002.png)",
            "concept",
            "DTC041204",
            "zh-CN",
            topic_kind="concept",
        )
        self.assertIn('<note type="warning">', xml)
        self.assertNotIn('image/docx_image_002.png', xml)


class BookmapTreeTest(unittest.TestCase):
    def test_nested_topics_keep_filenames_and_templates(self):
        lines = []
        node = {
            "topic": {
                "title": "产品信息",
                "filename": "CTO041001.dita",
                "id": "CTO041001",
                "topic_kind": "chapter",
            },
            "children": [
                {
                    "topic": {
                        "title": "实验前准备",
                        "filename": "DTC041002.dita",
                        "id": "DTC041002",
                        "topic_kind": "concept",
                    },
                    "children": [
                        {
                            "topic": {
                                "title": "准备试剂",
                                "filename": "DTO041003.dita",
                                "id": "DTO041003",
                                "topic_kind": "task",
                            },
                            "children": [],
                        }
                    ],
                }
            ],
        }

        _append_root_container_xml(
            lines,
            node,
            iter(range(1, 2)),
            iter(range(1, 10)),
            "  ",
            1,
            "20260811_090000",
            "zh-CN",
        )

        output = "\n".join(lines)
        self.assertIn('href="CTO041001.dita"', output)
        self.assertIn('cms:template="chapterTopic"', output)
        self.assertIn('href="DTC041002.dita"', output)
        self.assertIn('cms:template="sDitaConcept"', output)
        self.assertIn('href="DTO041003.dita"', output)
        self.assertIn('cms:template="sDitaTopic"', output)


class DocxMediaCopyTest(unittest.TestCase):
    def test_docx_media_is_copied_to_output_image_dir(self):
        import tempfile
        import zipfile

        with tempfile.TemporaryDirectory() as tmpdir:
            docx_path = Path(tmpdir) / "sample.docx"
            with zipfile.ZipFile(docx_path, "w") as zf:
                zf.writestr("word/media/image1.png", b"abc")
                zf.writestr("word/media/image2.jpg", b"def")

            output_base = Path(tmpdir) / "out"
            output_base.mkdir()

            copied = _copy_docx_media_to_output(str(docx_path), str(output_base))

            self.assertEqual(copied, {"image/docx_media_001.png", "image/docx_media_002.jpg"})
            self.assertTrue((output_base / "image" / "docx_media_001.png").exists())
            self.assertTrue((output_base / "image" / "docx_media_002.jpg").exists())


class ImageDownloadReuseTest(unittest.TestCase):
    def test_download_reuses_existing_output_image(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            output_base = Path(tmpdir) / "out"
            image_dir = output_base / "image"
            image_dir.mkdir(parents=True)
            existing = image_dir / "docx_media_001.png"
            existing.write_bytes(b"abc")

            mapping = _download_images_for_output([
                {"alt": "x", "path": str(existing)}
            ], str(output_base))

            self.assertEqual(mapping[str(existing)], "image/docx_media_001.png")


class DitaPackageTitleFilterTest(unittest.TestCase):
    def test_frontmatter_titles_are_filtered(self):
        import tempfile
        import zipfile

        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = Path(tmpdir) / "sample.zip"
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("sample.ditamap", '<topicref navtitle="封面CN" href="a.dita"/><topicref navtitle="正文" href="b.dita"/>')
                zf.writestr("a.dita", '<topic><title>A</title></topic>')
                zf.writestr("b.dita", '<topic><title>B</title></topic>')

            metrics = _parse_dita_package(zip_path)
            self.assertNotIn("封面CN", metrics["title_counts"])


if __name__ == "__main__":
    unittest.main()
