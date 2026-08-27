"""结构统计 + 工具指纹增量单测。

对应外部评审（Kimi/claw 意见）采纳项：
- 结构统计（客观指标）：页数/章节标题行/图片/表格/安全警告计数，报告新增独立章节；
- 指纹库增量：DITA-OT（PDF 元数据 + HTML 结构特征）与 Prince XML。
"""

import os
import tempfile
import unittest

from app.utils.competitor_analysis import (
    _match_producer,
    _is_heading_line,
    _is_warning_line,
    analyze_structure,
)
from app.utils.competitor_html import detect_html_tool, extract_main_text
from app.utils.competitor_report import render_competitor_report


class FingerprintDitaPrinceTestCase(unittest.TestCase):
    def test_dita_open_toolkit_producer(self):
        found = _match_producer("DITA Open Toolkit 4.2.1", "")
        self.assertIn("DITA-OT", [f["name"] for f in found])

    def test_dita_ot_short_forms(self):
        for producer in ("dita-ot 3.7.4", "ditaot"):
            found = _match_producer(producer, "")
            self.assertIn("DITA-OT", [f["name"] for f in found], producer)

    def test_oxygen_creator(self):
        found = _match_producer("", "oXygen XML Editor 26.1")
        self.assertIn("oXygen XML Editor", [f["name"] for f in found])

    def test_prince_producer(self):
        found = _match_producer("Prince 15.2", "")
        self.assertIn("Prince XML", [f["name"] for f in found])

    def test_dita_html_two_evidences_high(self):
        """URL 目录特征 + 类名特征 = 2 条独立证据 → high 置信。"""
        html = '<html><body><main><div class="topic"><h1>Install</h1></div></main></body></html>'
        extraction = extract_main_text(html)
        result = detect_html_tool("https://example.com/docs/topics/install.html", extraction, html)
        dita = [t for t in result["tools"] if t["name"] == "DITA-OT"]
        self.assertEqual(len(dita), 1)
        self.assertEqual(dita[0]["confidence"], "high")

    def test_dita_html_single_evidence_medium(self):
        html = '<html><body><p class="concept">x</p></body></html>'
        extraction = extract_main_text(html)
        result = detect_html_tool("https://example.com/manual/page.html", extraction, html)
        dita = [t for t in result["tools"] if t["name"] == "DITA-OT"]
        self.assertEqual(len(dita), 1)
        self.assertEqual(dita[0]["confidence"], "medium")

    def test_dita_no_false_positive_on_plain_page(self):
        extraction = extract_main_text("<html><body><main><h1>Hello</h1><p>world</p></main></body></html>")
        result = detect_html_tool("https://example.com/index.html", extraction, "")
        self.assertFalse([t for t in result["tools"] if t["name"] == "DITA-OT"])

    def test_dita_generator_merges_into_existing(self):
        """结构特征与 meta generator 同时命中时不产生重复条目，且证据并入。"""
        html = ('<html><head><meta name="generator" content="DITA Open Toolkit 4.2"></head>'
                '<body><main><div class="topic"><p>x</p></div></main></body></html>')
        extraction = extract_main_text(html)
        result = detect_html_tool("https://example.com/topics/a.html", extraction, html)
        dita = [t for t in result["tools"] if t["name"] == "DITA-OT"]
        self.assertEqual(len(dita), 1)
        self.assertEqual(dita[0]["confidence"], "high")
        self.assertTrue(any("generator" in e for e in dita[0]["evidence"]))


class FlareEvidenceTestCase(unittest.TestCase):
    """MadCap Flare 证据链补强（V1.2.2，实测 Illumina 全站具备）。

    新增两条证据：<html xmlns:MadCap> 根命名空间 + data-mc-help-system-file-name 属性。
    注意：data-mc-* 属性本身会先命中「HTML 含 data-mc-* 属性」证据，故帮助系统属性
    用例至少 2 条证据 → high；xmlns 单独命中为 1 条 → medium。
    """

    def test_flare_xmlns_namespace_evidence_medium(self):
        """仅 xmlns:MadCap 根命名空间 → 1 条新证据 → medium。"""
        html = ('<html xmlns:MadCap="http://www.madcapsoftware.com/Schemas/MadCap.xsd">'
                '<body><main><h1>Install the system</h1><p>Guide body text here.</p></main></body></html>')
        extraction = extract_main_text(html)
        result = detect_html_tool("https://example.com/page.html", extraction, html)
        flare = [t for t in result["tools"] if t["name"] == "MadCap Flare"]
        self.assertEqual(len(flare), 1)
        self.assertTrue(any("xmlns:MadCap" in e for e in flare[0]["evidence"]))
        self.assertEqual(flare[0]["confidence"], "medium")

    def test_flare_help_system_file_name_evidence(self):
        """data-mc-help-system-file-name → 帮助系统属性 + data-mc-* 属性两条证据 → high。"""
        html = ('<html data-mc-help-system-file-name="UserGuide_HTML5.flmsp">'
                '<body><main><h1>Install</h1><p>Guide body text.</p></main></body></html>')
        extraction = extract_main_text(html)
        result = detect_html_tool("https://example.com/page.html", extraction, html)
        flare = [t for t in result["tools"] if t["name"] == "MadCap Flare"]
        self.assertEqual(len(flare), 1)
        self.assertTrue(any("data-mc-help-system-file-name" in e for e in flare[0]["evidence"]))
        self.assertEqual(flare[0]["confidence"], "high")

    def test_flare_two_new_evidences_high(self):
        """两条 V1.2.2 新证据（命名空间 + 帮助系统属性）同时命中 → 证据齐全且 high。"""
        html = ('<html xmlns:MadCap="http://www.madcapsoftware.com/Schemas/MadCap.xsd" '
                'data-mc-help-system-file-name="UserGuide_HTML5.flmsp">'
                '<body><main><h1>Install</h1><p>Guide body text.</p></main></body></html>')
        extraction = extract_main_text(html)
        result = detect_html_tool("https://example.com/page.html", extraction, html)
        flare = [t for t in result["tools"] if t["name"] == "MadCap Flare"]
        self.assertEqual(len(flare), 1)
        self.assertEqual(flare[0]["confidence"], "high")
        evidence = flare[0]["evidence"]
        self.assertTrue(any("xmlns:MadCap" in e for e in evidence))
        self.assertTrue(any("data-mc-help-system-file-name" in e for e in evidence))


class StructureStatsTestCase(unittest.TestCase):
    def test_heading_line_heuristics(self):
        self.assertTrue(_is_heading_line("Chapter 3 Safety Precautions"))
        self.assertTrue(_is_heading_line("3.2 Instrument Installation"))
        self.assertTrue(_is_heading_line("第3章 安装与调试"))
        self.assertTrue(_is_heading_line("Appendix A Specifications"))
        # 编号步骤/句子/普通行不应误判为标题
        self.assertFalse(_is_heading_line("1. Connect the power cable."))
        self.assertFalse(_is_heading_line("Ensure the instrument is level before use."))
        self.assertFalse(_is_heading_line("2024-01-01"))
        self.assertFalse(_is_heading_line("a" * 80))

    def test_warning_line_heuristics(self):
        self.assertTrue(_is_warning_line("WARNING: Hot surface."))
        self.assertTrue(_is_warning_line("WARNING Hot surface"))
        self.assertTrue(_is_warning_line("CAUTION"))
        self.assertTrue(_is_warning_line("注意：断开电源后再维护"))
        # 句中出现的 warning 词不应计数（要求行首）；行首大写但后接小写单词为普通句
        self.assertFalse(_is_warning_line("The warning labels on the panel must remain legible."))
        self.assertFalse(_is_warning_line("WARNING signs indicate a potential hazard."))
        # 中文普通词组不应计数（交叉审查 P0-1 回归）：
        self.assertFalse(_is_warning_line("注意事项"))          # 常见标题，非警告块
        self.assertFalse(_is_warning_line("注意观察仪器状态"))    # 普通句子
        self.assertTrue(_is_warning_line("危险！高压电源"))       # 标签后接标点仍计

    def test_analyze_structure_text_only(self):
        text = "\n".join([
            "1 Introduction",
            "3.2 Instrument Installation",
            "WARNING: Hot surface.",
            "注意：断开电源",
            "Normal paragraph of the manual content.",
        ])
        stats = analyze_structure("note.docx", text, [text])
        self.assertEqual(stats["heading_count"], 1)   # "1 Introduction" 单级编号不算标题
        self.assertEqual(stats["warning_count"], 2)
        self.assertIsNone(stats["figure_count"])       # DOCX 暂不支持图片统计
        self.assertIsNone(stats["table_count"])
        self.assertTrue(any("仅支持" in n for n in stats["notes"]))

    def test_analyze_structure_html_extraction(self):
        extraction = {"img_count": 3, "table_count": 2, "heading_count": 4}
        stats = analyze_structure("page.html", "text", ["text"], html_extraction=extraction)
        self.assertEqual(stats["figure_count"], 3)
        self.assertEqual(stats["table_count"], 2)
        self.assertEqual(stats["heading_count"], 4)
        self.assertEqual(stats["page_count"], 1)

    def test_html_extractor_counts_content_elements(self):
        html = (
            "<html><body>"
            "<header><img src='logo.png'></header>"
            "<main><h1>Title</h1><h2>Section</h2><img src='a.png'><img src='b.png'>"
            "<table><tr><td>1</td></tr></table></main>"
            "<footer><table><tr><td>nav</td></tr></table></footer>"
            "</body></html>"
        )
        result = extract_main_text(html)
        self.assertEqual(result["img_count"], 2)      # header 中的 logo 不计
        self.assertEqual(result["table_count"], 1)    # footer 中的表格不计
        self.assertEqual(result["heading_count"], 2)

    def test_pdf_figure_and_table_counts(self):
        try:
            import fitz
        except ImportError:
            self.skipTest("PyMuPDF 不可用")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "sample.pdf")
            doc = fitz.open()
            page = doc.new_page()
            page.insert_text((72, 90), "1 Introduction")
            page.insert_text((72, 120), "3.2 Installation Steps")
            page.insert_text((72, 150), "WARNING: Hot surface.")
            # 3x3 线框表格（find_tables 需单元格内有文字才能识别线框）
            for i in range(4):
                y = 200 + i * 30
                page.draw_line(fitz.Point(200, y), fitz.Point(400, y))
                x = 200 + i * 60
                page.draw_line(fitz.Point(x, 200), fitz.Point(x, 290))
            for r in range(3):
                for c in range(3):
                    page.insert_text((210 + c * 60, 220 + r * 30), f"c{r}{c}")
            doc.save(path)
            doc.close()

            # 从生成的 PDF 取回文本（模拟真实流程：解析文本后再做结构统计）
            doc2 = fitz.open(path)
            pages_text = [p.get_text() for p in doc2]
            doc2.close()
            stats = analyze_structure(path, "\n".join(pages_text), pages_text)
            self.assertGreaterEqual(stats["page_count"], 1)
            if stats["table_count"] is not None:
                self.assertGreaterEqual(stats["table_count"], 1)
            # 文本指标同样工作
            self.assertEqual(stats["warning_count"], 1)


class StructureReportSectionTestCase(unittest.TestCase):
    def test_report_renders_structure_section(self):
        tool_analysis = {
            "summary": "主编辑工具：Adobe InDesign（high 置信）",
            "meta": {"format": "PDF 1.7", "pages": 12, "producer": "", "creator": ""},
            "tools": [],
            "font_signals": [],
            "text_signals": [],
            "structure_stats": {
                "page_count": 12, "heading_count": 9, "figure_count": 24,
                "table_count": 5, "warning_count": 7, "notes": [],
            },
        }
        readability = {
            "language": "en", "overall_score": 82.0, "level": "good", "level_note": "",
            "warnings": [], "dimensions": {}, "stats": {}, "suggestions": [],
        }
        md = render_competitor_report("x.pdf", tool_analysis, readability)
        self.assertIn("二、结构统计（客观指标）", md)
        self.assertIn("三、可读性分析", md)
        self.assertIn("24", md)
        # 无结构统计时不渲染空章节
        tool_analysis.pop("structure_stats")
        md2 = render_competitor_report("x.pdf", tool_analysis, readability)
        self.assertNotIn("二、结构统计", md2)


class PdfTableDetectionFallbackTestCase(unittest.TestCase):
    def test_find_tables_unavailable_returns_none_with_note(self):
        """旧版 PyMuPDF 无 find_tables：返回 None + 说明，不能静默当 0（交叉审查 P1-2）。"""
        from app.utils.competitor_analysis import _count_pdf_tables

        class _FakePage:  # 无 find_tables 属性
            pass

        class _FakeDoc:
            page_count = 3

            def __getitem__(self, i):
                return _FakePage()

        count, note = _count_pdf_tables(_FakeDoc())
        self.assertIsNone(count)
        self.assertIn("不支持", note)


class RunAnalysisInjectionTestCase(unittest.TestCase):
    def test_run_analysis_injects_structure_stats_for_html(self):
        """_run_analysis 全链路：HTML 上下文的结构计数进入 tool_analysis（交叉审查 P1-5）。"""
        import os as _os
        import tempfile as _tf
        from app.api.competitor import _run_analysis

        html = ("<html><body><main><h1>Install</h1><img src='a.png'>"
                "<table><tr><td>1</td></tr></table>"
                "<p>WARNING: Hot surface during operation of the instrument.</p></main></body></html>")
        from app.utils.competitor_html import extract_main_text
        extraction = extract_main_text(html)
        with _tf.TemporaryDirectory() as tmp:
            path = _os.path.join(tmp, "page.html")
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
            result = _run_analysis(
                path, "page.html", extraction["full_text"], [extraction["full_text"]],
                html_context={"final_url": "", "html": html, "extraction": extraction},
            )
        stats = result["tool_analysis"].get("structure_stats") or {}
        self.assertEqual(stats.get("figure_count"), 1)
        self.assertEqual(stats.get("table_count"), 1)
        self.assertEqual(stats.get("heading_count"), 1)
        self.assertEqual(stats.get("warning_count"), 1)
        # 报告同时包含结构统计章节与重排后的可读性章节
        self.assertIn("二、结构统计（客观指标）", result["report_md"])
        self.assertIn("三、可读性分析", result["report_md"])
        self.assertIn("七、对本司的启示", result["report_md"])


if __name__ == "__main__":
    unittest.main()
