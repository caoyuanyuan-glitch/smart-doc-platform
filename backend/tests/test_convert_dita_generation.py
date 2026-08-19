import sys
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.api.convert import (  # noqa: E402
    _append_bookmap_topics,
    _append_root_container_xml,
    _build_topic_hierarchy,
    _content_to_dita_xml,
    _extract_template_frontmatter_subset,
    _docx_to_markdown,
    _docx_table_to_markdown,
    _looks_like_docx_heading_text,
    _parse_md_sections,
    _postprocess_section_tree,
    _reshape_docx_sections,
    _generated_topic_code,
    _copy_docx_media_to_output,
    _download_images_for_output,
    _topic_placeholder,
    _rewrite_template_frontmatter,
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
            "警告：吸取上清并丢弃。\n请勿触碰磁珠。",
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
        self.assertIn('<table>\n          <title>Fe (II) 稀释液配置</title>', xml)

    def test_adjacent_tables_keep_their_own_titles(self):
        xml = _content_to_dita_xml(
            "连续表格",
            "表 11 试剂准备\n| 试剂名称 | 要求 |\n| :--- | :--- |\n| TE Buffer | 室温暂存 |\n\n表 12 样本准备\n| 样本名称 | 用途 |\n| :--- | :--- |\n| DNA | 待检测 |",
            "concept",
            "DTC041205",
            "zh-CN",
            topic_kind="concept",
        )
        self.assertIn('<title>试剂准备</title>', xml)
        self.assertIn('<title>样本准备</title>', xml)

    def test_table_number_and_following_line_form_title(self):
        xml = _content_to_dita_xml(
            "Components",
            "Table 2\nMGIEasy Whole Genome Methylation Sequencing Library Prep Kit (16 RXN) (Cat. No.: 940-001530-00)\n| Item | Component |\n| :--- | :--- |\n| A | B |",
            "concept",
            "DTC041212",
            "en-US",
            topic_kind="concept",
        )
        self.assertIn('<title>MGIEasy Whole Genome Methylation Sequencing Library Prep Kit (16 RXN) (Cat. No.: 940-001530-00)</title>', xml)

    def test_table_caption_without_table_body_is_preserved_as_paragraph(self):
        xml = _content_to_dita_xml(
            "Annealing",
            "Table 58 Annealing reaction mix\n1. Place the conditions.",
            "task",
            "DTO041213",
            "en-US",
            topic_kind="task",
        )
        self.assertIn('<p>Table 58 Annealing reaction mix</p>', xml)
        self.assertNotIn('<table>', xml)

    def test_embedded_table_caption_row_splits_into_next_table(self):
        xml = _content_to_dita_xml(
            "Barcode using guide",
            "Table 73 Perfect balanced 8 barcode Pooling strategy (8 barcode from one entire column)\n| Sample 1 | A | G |\n| :--- | :--- | :--- |\n| Signal % | 25.0 | 25.0 |\n| Table 74 Unbalanced 9 barcode Poolin |  | g strategy (barcode from different columns) |\n| Sample 1 | A | T |\n| A signal % | 33.3 | 0 |",
            "concept",
            "DTC041222",
            "en-US",
            topic_kind="concept",
        )
        self.assertEqual(xml.count('<table>'), 2)
        self.assertIn('<title>Perfect balanced 8 barcode Pooling strategy (8 barcode from one entire column)</title>', xml)
        self.assertIn('<title>Unbalanced 9 barcode Pooling strategy (barcode from different columns)</title>', xml)

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

    def test_note_with_unordered_list_stays_inside_note(self):
        xml = _content_to_dita_xml(
            "准备",
            "注意事项：\n- 提示一\n- 提示二",
            "concept",
            "DTC041225",
            "zh-CN",
            topic_kind="concept",
        )
        self.assertIn('<note type="tip">', xml)
        self.assertIn('<ul>', xml)
        self.assertIn('提示一', xml)
        self.assertIn('提示二', xml)
        self.assertIn('<note type="tip">\n        <ul>', xml)

    def test_figure_caption_wraps_pending_image(self):
        xml = _content_to_dita_xml(
            "图片示例",
            "![docx_image_001.png](image/docx_image_001.png)\n图 1 示例图片",
            "concept",
            "DTC041203",
            "zh-CN",
            topic_kind="concept",
        )
        self.assertIn('<fig><title>图 1 示例图片</title><image href="image/docx_image_001.png" placement="break"></image></fig>', xml)
        self.assertNotIn('<alt>', xml)

    def test_english_figure_caption_drops_number_prefix(self):
        xml = _content_to_dita_xml(
            "Figure demo",
            "![docx_image_001.png](image/docx_image_001.png)\nFigure 7 PCR BC Primer-96 layout",
            "concept",
            "DTC041217",
            "en-US",
            topic_kind="concept",
        )
        self.assertIn('<fig><title>PCR BC Primer-96 layout</title><image href="image/docx_image_001.png" placement="break"></image></fig>', xml)
        self.assertNotIn('Figure 7', xml)

    def test_inline_sup_markup_becomes_sup_tag(self):
        xml = _content_to_dita_xml(
            "About",
            "Agilent[[SUP]]®[[/SUP]] and Thermo Fisher[[SUP]]™[[/SUP]] are trademarks.",
            "concept",
            "DTC041223",
            "en-US",
            topic_kind="concept",
        )
        self.assertIn('<p>Agilent<sup>®</sup> and Thermo Fisher<sup>™</sup> are trademarks.</p>', xml)

    def test_inline_bold_markup_becomes_b_tag(self):
        xml = _content_to_dita_xml(
            "Purity",
            "It is strongly recommended to use [[B]]high quality DNA[[/B]] for library preparation.",
            "concept",
            "DTC041224",
            "en-US",
            topic_kind="concept",
        )
        self.assertIn('<p>It is strongly recommended to use <b>high quality DNA</b> for library preparation.</p>', xml)

    def test_ordered_list_keeps_embedded_blocks_in_same_ol(self):
        xml = _content_to_dita_xml(
            "步骤示例",
            "1. 第一步\n![docx_image_001.png](image/docx_image_001.png)\n图 1 示例图片\n警告：保持低温。\n表 1 参数\n| 名称 | 值 |\n| :--- | :--- |\n| 温度 | 4℃ |\n2. 第二步",
            "task",
            "DTO041210",
            "zh-CN",
            topic_kind="task",
        )
        self.assertEqual(xml.count('<ol>'), 1)
        self.assertIn('<li><p>第一步</p>', xml)
        self.assertIn('<fig><title>图 1 示例图片</title><image href="image/docx_image_001.png" placement="break"></image></fig>', xml)
        self.assertIn('<note type="warning"><p>保持低温。</p></note>', xml)
        self.assertIn('<table>\n          <title>参数</title>', xml)
        self.assertIn('<li>第二步</li>', xml)

    def test_standalone_image_has_no_alt_tag(self):
        xml = _content_to_dita_xml(
            "图片示例",
            "![docx_image_003.png](image/docx_image_003.png)",
            "concept",
            "DTC041211",
            "zh-CN",
            topic_kind="concept",
        )
        self.assertIn('<image href="image/docx_image_003.png" placement="break"></image>', xml)
        self.assertNotIn('<alt>', xml)

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

    def test_english_warning_paragraph_becomes_note(self):
        xml = _content_to_dita_xml(
            "Cleanup",
            "WARNING: Keep the tube on ice.",
            "concept",
            "DTC041214",
            "en-US",
            topic_kind="concept",
        )
        self.assertIn('<note type="warning"><p>Keep the tube on ice.</p></note>', xml)

    def test_stoppoint_paragraph_becomes_note(self):
        xml = _content_to_dita_xml(
            "Cleanup",
            "StopPoint: Store at -20C for up to 24 h.",
            "concept",
            "DTC041216",
            "en-US",
            topic_kind="concept",
        )
        self.assertIn('<note type="tip"><p>Store at -20C for up to 24 h.</p></note>', xml)

    def test_multiline_english_note_uses_icon_line_and_following_text(self):
        xml = _content_to_dita_xml(
            "Cleanup",
            "Stop point.\n![docx_image_016.png](/workspace/H-940-001530-00-01 MGIEasy Whole Genome Methylation Sequencing Library Prep Kit User Manual 3.0-2503_media/docx_image_016.png)\nProduct(s) can be stored at -20 C.",
            "concept",
            "DTC041218",
            "en-US",
            topic_kind="concept",
        )
        self.assertIn('<note type="tip">', xml)
        self.assertIn('<p>Product(s) can be stored at -20 C.</p>', xml)
        self.assertNotIn('docx_image_016.png', xml)

    def test_warning_text_with_icon_becomes_warning_note(self):
        xml = _content_to_dita_xml(
            "QC",
            "Do not perform multi-sample pooling with PCR product.\n![docx_image_109.png](/workspace/H-940-001530-00-01 MGIEasy Whole Genome Methylation Sequencing Library Prep Kit User Manual 3.0-2503_media/docx_image_109.png)",
            "concept",
            "DTC041219",
            "en-US",
            topic_kind="concept",
        )
        self.assertIn('<note type="warning"><p>Do not perform multi-sample pooling with PCR product.</p></note>', xml)
        self.assertNotIn('docx_image_109.png', xml)

    def test_stop_point_with_only_page_number_tail_is_dropped(self):
        xml = _content_to_dita_xml(
            "Workflow",
            "- Stop point.\n![docx_image_016.png](/workspace/H-940-001530-00-01 MGIEasy Whole Genome Methylation Sequencing Library Prep Kit User Manual 3.0-2503_media/docx_image_016.png)\n9",
            "concept",
            "DTC041220",
            "en-US",
            topic_kind="concept",
        )
        self.assertNotIn('<note type="tip"><p>Stop point</p></note>', xml)
        self.assertNotIn('<p>9</p>', xml)

    def test_plain_page_number_paragraph_is_dropped(self):
        xml = _content_to_dita_xml(
            "Appendix",
            "正文段落\n\n12",
            "concept",
            "DTC041221",
            "zh-CN",
            topic_kind="concept",
        )
        self.assertIn('<p>正文段落</p>', xml)
        self.assertNotIn('<p>12</p>', xml)

    def test_page_reference_in_sentence_is_removed(self):
        xml = _content_to_dita_xml(
            "Barcode using guide (96 RXN)",
            "1. For sample numbers < 8 with the same data volume, refer to Appendix on page 51 to select barcodes.",
            "concept",
            "DTC041226",
            "en-US",
            topic_kind="concept",
        )
        self.assertIn('refer to Appendix to select barcodes.', xml)
        self.assertNotIn('page 51', xml)

    def test_duplicate_table_header_row_is_removed(self):
        xml = _content_to_dita_xml(
            "Workflow",
            "Table 1 Workflow\n| Section | Workflow | Hands-on time | Total time |\n| :--- | :--- | :--- | :--- |\n| 2.1 | Sample shearing | 2 min | 10 min |\n| Section | Workflow | Hands-on time | Total time |\n| 2.2 | Cleanup | 5 min | 20 min |",
            "concept",
            "DTC041227",
            "en-US",
            topic_kind="concept",
        )
        self.assertEqual(xml.count('<entry>Section</entry>'), 1)
        self.assertIn('<entry>2.2</entry>', xml)

    def test_repeated_grouped_first_column_is_collapsed_in_table_body(self):
        xml = _content_to_dita_xml(
            "Components",
            "Table 2 Components\n| Item & Cat. No. | Component | Spec |\n| :--- | :--- | :--- |\n| Module A | Buffer | 10 uL |\n| Module A | Enzyme | 20 uL |",
            "concept",
            "DTC041228",
            "en-US",
            topic_kind="concept",
        )
        self.assertIn('<entry>Module A</entry>', xml)
        self.assertIn('<entry></entry>\n                <entry>Enzyme</entry>', xml)

    def test_first_body_row_that_only_repeats_header_prefix_is_removed(self):
        xml = _content_to_dita_xml(
            "Shearing condition",
            """Table 68 Conditions
| S220 | Vessel | microTUBE |
| :--- | :--- | :--- |
| S220 | Vessel | |
|  | Sample Volume | 55 μL |""",
            "concept",
            "DTC041229",
            "en-US",
            topic_kind="concept",
        )
        self.assertEqual(xml.count('<entry>S220</entry>'), 1)
        self.assertIn('<entry>Sample Volume</entry>', xml)

    def test_do_not_sentence_stays_paragraph(self):
        xml = _content_to_dita_xml(
            "Cleanup",
            "Do not touch the magnetic beads.",
            "concept",
            "DTC041215",
            "en-US",
            topic_kind="concept",
        )
        self.assertIn('<p>Do not touch the magnetic beads.</p>', xml)
        self.assertNotIn('<note type="warning">', xml)


class DocxHeadingDetectionTest(unittest.TestCase):
    def test_numbered_short_title_is_recognized_as_heading(self):
        self.assertTrue(_looks_like_docx_heading_text('6.2.3 Sample Barcode 使⽤规则 (96 RXN)'))

    def test_parenthesized_short_title_is_recognized_as_heading(self):
        self.assertTrue(_looks_like_docx_heading_text('DNB 加载 (StandardMPS 2.0)'))

    def test_formula_line_is_not_recognized_as_heading(self):
        self.assertFalse(_looks_like_docx_heading_text('Formula 1 Conversion between 1 pmol of PCR product and mass in ng'))
        self.assertFalse(_looks_like_docx_heading_text('Sample mass (ng) = Sample concentration (ng/μL) × Sample volume (μL)'))

    def test_bold_table_caption_is_not_recognized_as_heading(self):
        self.assertFalse(_looks_like_docx_heading_text('[[B]]Table[[/B]][[B]] [[/B]][[B]]10[[/B]][[B]] [[/B]][[B]]Workflow[[/B]]'))

    def test_reshape_keeps_numbered_docx_heading_as_separate_topic(self):
        markdown = "# Barcode 引物使⽤注意\n\n1. 规则 A\n\n### 6.2.3 Sample Barcode 使⽤规则 (96 RXN)\n\n1. 规则 B\n"
        sections = _postprocess_section_tree(_reshape_docx_sections(_parse_md_sections(markdown)))
        root = sections[0]
        child_titles = [child.get('title') for child in root.get('sections', [])]
        self.assertIn('6.2.3 Sample Barcode 使⽤规则 (96 RXN)', child_titles)

    def test_parenthesized_docx_heading_becomes_separate_section(self):
        markdown = "# MGISEQ-2000RS DNB 加载\n\n### DNB 加载 (StandardMPS)\n\n#### 准备\n\n试剂说明\n"
        sections = _postprocess_section_tree(_reshape_docx_sections(_parse_md_sections(markdown)))
        root = sections[0]
        child_titles = [child.get('title') for child in root.get('sections', [])]
        self.assertIn('DNB 加载 (StandardMPS)', child_titles)

    def test_real_docx_markdown_contains_expected_split_headings(self):
        markdown = _docx_to_markdown('/workspace/.monkeycode-tmp-files/8a916735-H-940-001530-00 MGIEasy 全基因组甲基化建库试剂盒使用说明书 3.0 -250317-1.docx')
        self.assertIn('## Barcode 引物使⽤注意', markdown)

    def test_real_docx_markdown_merges_wrapped_sentence_fragments(self):
        markdown = _docx_to_markdown('/workspace/.monkeycode-tmp-files/8a916735-H-940-001530-00 MGIEasy 全基因组甲基化建库试剂盒使用说明书 3.0 -250317-1.docx')
        self.assertIn('1. 将样本管瞬时离心，再置于磁力架上静置 2~5 min 至液体澄清，小心吸取上清并丢弃。', markdown)
        self.assertNotIn('将样本管瞬时离心，再置于磁力架上静置 2~5 min 至液体澄清，\n\n小心吸取上清并丢弃。', markdown)
        self.assertNotIn('将样本管瞬时离心，再置于磁力架上静置 2~5 min 至液体澄清，\n小心吸取上清并丢弃。', markdown)

    def test_real_docx_markdown_preserves_superscript_placeholders(self):
        markdown = _docx_to_markdown('/workspace/H-940-001530-00-01 MGIEasy Whole Genome Methylation Sequencing Library Prep Kit User Manual 3.0-2503.docx')
        self.assertIn('Agilent[[SUP]]®[[/SUP]]', markdown)

    def test_real_docx_markdown_preserves_bold_placeholders(self):
        markdown = _docx_to_markdown('/workspace/H-940-001530-00-01 MGIEasy Whole Genome Methylation Sequencing Library Prep Kit User Manual 3.0-2503.docx')
        self.assertIn('[[B]]Revision[[/B]][[B]] [[/B]][[B]]history[[/B]]', markdown)

    def test_topic_title_attribute_strips_inline_bold_placeholders(self):
        xml = _content_to_dita_xml(
            '[[B]]Table[[/B]][[B]] [[/B]][[B]]10[[/B]][[B]] [[/B]][[B]]Workflow[[/B]]',
            '',
            'concept',
            'DTC999999',
            'en-US',
            topic_kind='concept',
        )
        self.assertIn('cms:title="Table 10 Workflow"', xml)
        self.assertIn('<title id="title_DTC999999">Table 10 Workflow</title>', xml)

    def test_wrapped_sentence_keeps_independent_explanation_line(self):
        from app.api.convert import _merge_docx_wrapped_paragraphs

        lines = [
            '1. 将样本管从磁力架上取下，加入 32 μL TE Buffer 进行 DNA 洗脱',
            '',
            '也可根据实际需求，适当减少洗脱体积。',
        ]
        self.assertEqual(_merge_docx_wrapped_paragraphs(lines), lines)


class SectionPostprocessTest(unittest.TestCase):
    def test_same_named_bold_table_section_copies_content_to_parent(self):
        sections = _postprocess_section_tree([
            {
                "title": "Workflow",
                "content": "",
                "sections": [
                    {
                        "title": "[[B]]Table[[/B]][[B]] [[/B]][[B]]10[[/B]][[B]] [[/B]][[B]]Workflow[[/B]]",
                        "content": "| Section | Workflow |",
                        "sections": [],
                    }
                ],
            }
        ])
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0]["title"], "Workflow")
        self.assertIn('| Section | Workflow |', sections[0]["content"])
        self.assertEqual(len(sections[0]["sections"]), 1)
        self.assertEqual(sections[0]["sections"][0]["title"], '[[B]]Table[[/B]][[B]] [[/B]][[B]]10[[/B]][[B]] [[/B]][[B]]Workflow[[/B]]')


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

    def test_topic_hierarchy_uses_levels_for_nesting(self):
        topics = [
            {"title": "Cover", "filename": "CTT041001.dita", "id": "CTT041001", "topic_kind": "cover", "level": 1},
            {"title": "About the user manual", "filename": "CTO041002.dita", "id": "CTO041002", "topic_kind": "chapter", "level": 2},
            {"title": "Manufacturer information", "filename": "DTC041003.dita", "id": "DTC041003", "topic_kind": "concept", "level": 2},
            {"title": "Contact information", "filename": "DTC041004.dita", "id": "DTC041004", "topic_kind": "concept", "level": 3},
        ]

        roots = _build_topic_hierarchy(topics, set())
        self.assertEqual([node["topic"]["title"] for node in roots], ["Cover"])
        self.assertEqual([node["topic"]["title"] for node in roots[0]["children"]], ["About the user manual", "Manufacturer information"])
        self.assertEqual([node["topic"]["title"] for node in roots[0]["children"][1]["children"]], ["Contact information"])

    def test_frontmatter_topics_after_cover_attach_under_cover(self):
        import re

        lines = []
        topic_roots = [
            {"topic": {"title": "Cover", "filename": "CTT041001.dita", "id": "CTT041001", "topic_kind": "cover"}, "children": []},
            {"topic": {"title": "About the user manual", "filename": "DTC041002.dita", "id": "DTC041002", "topic_kind": "concept"}, "children": []},
            {"topic": {"title": "Manufacturer information", "filename": "DTC041003.dita", "id": "DTC041003", "topic_kind": "concept"}, "children": []},
            {"topic": {"title": "Revision history", "filename": "DTC041004.dita", "id": "DTC041004", "topic_kind": "concept"}, "children": []},
            {"topic": {"title": "Product overview", "filename": "CTO041005.dita", "id": "CTO041005", "topic_kind": "chapter"}, "children": []},
        ]

        _append_bookmap_topics(lines, topic_roots, "20260813_120000", "en-US")
        output = "\n".join(lines)

        self.assertEqual(output.count('navtitle="About the user manual"'), 1)
        self.assertEqual(output.count('navtitle="Manufacturer information"'), 1)
        self.assertEqual(output.count('navtitle="Revision history"'), 1)
        cover_block = re.search(r'<frontmatter[\s\S]*?</frontmatter>', output)
        self.assertIsNotNone(cover_block)
        frontmatter_xml = cover_block.group(0)
        self.assertIn('navtitle="About the user manual"', frontmatter_xml)
        self.assertIn('navtitle="Manufacturer information"', frontmatter_xml)
        self.assertIn('navtitle="Revision history"', frontmatter_xml)


class TemplateSubsetTest(unittest.TestCase):
    def test_frontmatter_subset_keeps_cover_and_booklists_only(self):
        xml = '''<frontmatter navtitle="Preface">
  <topicref navtitle="Old Cover" href="cover.dita"/>
  <topicref navtitle="About" href="about.dita"/>
  <booklists><toc/></booklists>
</frontmatter>'''
        subset = _extract_template_frontmatter_subset(xml)
        self.assertIn('href="cover.dita"', subset)
        self.assertIn('<booklists><toc/></booklists>', subset)
        self.assertNotIn('href="about.dita"', subset)

    def test_rewrite_frontmatter_attaches_cover_children(self):
        xml = '<frontmatter><topicref navtitle="Old Cover" href="cover.dita" keys="OLD" cms:title="Old Cover" cms:placeHolder="cover"/></frontmatter>'
        topics = [
            {"title": "Cover", "filename": "CTT041001.dita", "id": "CTT041001", "topic_kind": "cover", "level": 1},
            {"title": "About the user manual", "filename": "DTC041002.dita", "id": "DTC041002", "topic_kind": "concept", "level": 2},
            {"title": "Manufacturer information", "filename": "DTC041003.dita", "id": "DTC041003", "topic_kind": "concept", "level": 2},
            {"title": "Revision history", "filename": "DTC041004.dita", "id": "DTC041004", "topic_kind": "concept", "level": 2},
        ]
        rewritten, used_files = _rewrite_template_frontmatter(xml, topics)
        self.assertIn('href="cover.dita"', rewritten)
        self.assertIn('href="DTC041002.dita"', rewritten)
        self.assertIn('href="DTC041003.dita"', rewritten)
        self.assertIn('href="DTC041004.dita"', rewritten)
        self.assertEqual(used_files, {"cover.dita", "DTC041002.dita", "DTC041003.dita", "DTC041004.dita"})


class DocxTableMarkdownTest(unittest.TestCase):
    def test_repeated_merged_cell_values_are_collapsed(self):
        tc_objects = {}

        class Cell:
            def __init__(self, text, tc_id):
                self.text = text
                self._tc = tc_objects.setdefault(tc_id, object())

        class Row:
            def __init__(self, cells):
                self.cells = [Cell(text, tc_id) for text, tc_id in cells]

        class Table:
            def __init__(self, rows):
                self.rows = [Row(row) for row in rows]

        table = Table([
            [["Component", 1], ["Volume", 2]],
            [["Buffer", 3], ["10 uL", 4]],
            [["Buffer", 3], ["20 uL", 5]],
        ])

        lines = _docx_table_to_markdown(table)
        self.assertEqual(lines[2], '| Buffer | 10 uL |')
        self.assertEqual(lines[3], '| Buffer | 20 uL |')

    def test_merged_cell_does_not_clear_nonmerged_neighbor_content(self):
        tc_objects = {}

        class Cell:
            def __init__(self, text, tc_id):
                self.text = text
                self._tc = tc_objects.setdefault(tc_id, object())

        class Row:
            def __init__(self, cells):
                self.cells = [Cell(text, tc_id) for text, tc_id in cells]

        class Table:
            def __init__(self, rows):
                self.rows = [Row(row) for row in rows]

        table = Table([
            [["A", 1], ["B", 2], ["C", 3]],
            [["A", 4], ["Merged", 5], ["Tail 1", 6]],
            [["D", 7], ["Merged", 5], ["Tail 2", 8]],
        ])

        lines = _docx_table_to_markdown(table)
        self.assertEqual(lines[2], '| A | Merged | Tail 1 |')
        self.assertEqual(lines[3], '| D | Merged | Tail 2 |')

    def test_identical_text_without_shared_cell_object_is_preserved(self):
        class Cell:
            def __init__(self, text):
                self.text = text
                self._tc = object()

        class Row:
            def __init__(self, cells):
                self.cells = [Cell(text) for text in cells]

        class Table:
            def __init__(self, rows):
                self.rows = [Row(row) for row in rows]

        table = Table([
            ["Component", "Volume"],
            ["Buffer", "10 uL"],
            ["Buffer", "20 uL"],
        ])

        lines = _docx_table_to_markdown(table)
        self.assertEqual(lines[2], '| Buffer | 10 uL |')
        self.assertEqual(lines[3], '| Buffer | 20 uL |')


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
