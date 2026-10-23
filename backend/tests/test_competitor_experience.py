"""体验三维度分析单测：可获得性（Access）/ 易查找性（Findability）/ 可用性（Usability）。

对应需求说明书 V1.2 §3.3-3.5 与《Developing Quality Technical Information》质量特征：
- HTML 输入全维度可检（自动）；
- PDF 输入站内搜索/移动端/多语言/URL/SEO 等维度 N/A（applicable=False + score=None + notes 注明）；
- 综合评分 = 适用维度加权平均（N/A 权重不计入分母）；
- 每维度输出定性分级（grade）+ 0-100 评分（score）。
"""

import os
import tempfile
import unittest

from app.utils.competitor_experience import (
    analyze_access,
    analyze_experience,
    analyze_findability,
    analyze_usability,
    _detect_login_form,
    _detect_mobile,
    _detect_languages,
    _detect_search,
    _detect_version,
    _detect_breadcrumb,
    _detect_toc,
    _detect_index_glossary,
    _detect_quick_links,
    _url_semantic,
    _seo_metadata,
    _task_oriented_headings,
    _step_completeness,
    _detect_error_recovery,
    _consistency,
    _imperative_instructions,
    _link_validity,
    _same_site,
    _aggregate,
    _na_notes,
)
from app.utils.competitor_report import render_competitor_report
from bs4 import BeautifulSoup

# 功能完整的 HTML：覆盖 Access/Findability 全维度可检要素
FULL_HTML = """<html lang="en">
<head>
  <title>NextSeq 1000/2000 User Guide</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="NextSeq 1000/2000 sequencing system user guide">
  <link rel="canonical" href="https://docs.example.com/nextseq/guide.html">
</head>
<body>
  <nav aria-label="breadcrumb"><ol><li><a href="/">Home</a></li><li><a href="/nextseq">NextSeq</a></li><li>User Guide</li></ol></nav>
  <form role="search"><input type="search" name="q" placeholder="Search"></form>
  <nav class="toc"><ul><li><a href="#install">1.1 Installing the System</a></li><li><a href="#run">1.2 Running a Run</a></li></ul></nav>
  <main>
    <h1>NextSeq 1000/2000 User Guide</h1>
    <p>Version 1.2, document number 200027171, released 2024-03-15</p>
    <h2>1. Installing the System</h2>
    <p>Before you begin, verify the site requirements.</p>
    <ol>
      <li>Place the instrument in the lab.</li>
      <li>Connect the power cord.</li>
      <li>Install the software.</li>
    </ol>
    <p>Expected result: the system powers on and shows the home screen.</p>
    <h2>2. Troubleshooting</h2>
    <p>Common error codes are listed in the appendix.</p>
    <a href="/docs/guide.pdf">PDF manual</a>
    <a href="/docs/guide.docx">Word manual</a>
    <a href="/docs/guide.epub">EPUB manual</a>
    <a href="/glossary">Glossary</a>
    <a href="/index">Index</a>
  </main>
</body>
</html>"""

FULL_TEXT = """NextSeq 1000/2000 User Guide
Version 1.2, document number 200027171, released 2024-03-15
1. Installing the System
Before you begin, verify the site requirements.
1) Place the instrument in the lab.
2) Connect the power cord.
3) Install the software.
Expected result: the system powers on.
2. Troubleshooting
Common error codes are listed in the appendix.
"""


def _soup(html):
    return BeautifulSoup(html or "", "html.parser")


class AccessTestCase(unittest.TestCase):
    """可获得性：获取门槛/格式选择/搜索/移动端/多语言/版本/离线。"""

    def test_login_form_detection(self):
        soup = _soup('<form><input type="text" name="user"><input type="password" name="pass"></form>')
        grade, score = _detect_login_form(soup)
        self.assertEqual(score, 40)
        self.assertIn("登录", grade)

    def test_email_gate_detection(self):
        soup = _soup('<form><input type="email" name="mail"></form>')
        grade, score = _detect_login_form(soup)
        self.assertEqual(score, 70)
        self.assertIn("邮箱", grade)

    def test_no_gate(self):
        soup = _soup('<form><input type="text" name="q"></form>')
        grade, score = _detect_login_form(soup)
        self.assertEqual(score, 100)
        self.assertEqual(grade, "无门槛")

    def test_mobile_responsive(self):
        html = '<html><head><meta name="viewport" content="width=device-width"></head><body><style>@media (max-width: 600px){}</style></body></html>'
        grade, score = _detect_mobile(_soup(html), html)
        self.assertEqual(score, 100)
        self.assertEqual(grade, "响应式")

    def test_mobile_none(self):
        grade, score = _detect_mobile(_soup("<html><body></body></html>"), "")
        self.assertEqual(score, 30)
        self.assertEqual(grade, "无适配")

    def test_search_input_detected(self):
        grade, score = _detect_search(_soup('<input type="search" name="q">'))
        self.assertEqual(score, 100)
        self.assertEqual(grade, "有")

    def test_search_absent(self):
        grade, score = _detect_search(_soup('<input type="text" name="foo">'))
        self.assertEqual(score, 0)

    def test_search_hat_root_attribute_detected(self):
        """V1.2.2：MadCap Flare 等 HAT 在 <html data-mc-search-type> 声明站内搜索
        （UI 由 JS 注入、静态 DOM 无输入框），识别根属性视为有站内搜索。"""
        soup = _soup('<html data-mc-search-type="Stem"><body><main><h1>Install</h1></main></body></html>')
        grade, score = _detect_search(soup)
        self.assertEqual(score, 100)
        self.assertIn("HAT", grade)

    def test_search_hat_attribute_no_false_positive(self):
        """根属性为空/缺省时仍走常规检测，不误报。"""
        soup = _soup('<html data-mc-search-type=""><body><input type="text" name="foo"></body></html>')
        grade, score = _detect_search(soup)
        self.assertEqual(score, 0)
        self.assertEqual(grade, "无")

    def test_version_transparency(self):
        grade, score = _detect_version("See document number 200027171 for details.")
        self.assertEqual(score, 100)
        grade2, score2 = _detect_version("This is a plain manual without versioning.")
        self.assertEqual(score2, 0)

    def test_access_html_all_dimensions(self):
        result = analyze_access("page.html", FULL_TEXT, html=FULL_HTML, final_url="https://docs.example.com/nextseq/guide.html")
        dims = result["dimensions"]
        # 全维度适用
        for key in ("access_barrier", "formats", "has_search", "mobile_adaptation",
                    "languages", "version_transparency", "offline_available"):
            self.assertTrue(dims[key]["applicable"], key)
            self.assertIsNotNone(dims[key]["score"], key)
        self.assertGreaterEqual(result["overall_score"], 0)
        # 下载链接存在 → 多格式 + 可离线
        self.assertEqual(dims["formats"]["score"], 100)
        self.assertEqual(dims["offline_available"]["score"], 100)

    def test_access_pdf_na_dimensions(self):
        result = analyze_access("manual.pdf", FULL_TEXT, pages_text=[FULL_TEXT])
        dims = result["dimensions"]
        for key in ("access_barrier", "has_search", "mobile_adaptation", "languages"):
            self.assertFalse(dims[key]["applicable"], key)
            self.assertIsNone(dims[key]["score"], key)
        # PDF 可检测维度正常
        self.assertTrue(dims["formats"]["applicable"])
        self.assertTrue(dims["version_transparency"]["applicable"])
        self.assertTrue(dims["offline_available"]["applicable"])
        self.assertTrue(result["notes"], "PDF 输入应有 N/A 说明")
        # 综合评分 = 适用维度加权平均（3 个 N/A 不计分母）
        self.assertIsNotNone(result["overall_score"])


class FindabilityTestCase(unittest.TestCase):
    """易查找性：搜索/目录/面包屑/索引/URL/SEO/直达。"""

    def test_toc_html_deep_heading(self):
        html = "<html><body>" + "".join(f"<h{i}>{i}</h{i}>" for i in range(1, 5)) + "</body></html>"
        grade, score, extra = _detect_toc(_soup(html), "", "page.html")
        self.assertEqual(score, 100)
        self.assertIn("4", extra["note"])

    def test_toc_html_shallow(self):
        html = "<html><body><h1>A</h1><h2>B</h2></body></html>"
        grade, score, _ = _detect_toc(_soup(html), "", "page.html")
        self.assertEqual(score, 60)

    def test_breadcrumb_detected(self):
        html = '<nav aria-label="breadcrumb"><ol><li><a href="/">H</a></li><li><a href="/a">A</a></li><li>B</li></ol></nav>'
        grade, score = _detect_breadcrumb(_soup(html))
        self.assertEqual(score, 100)

    def test_index_glossary_detected(self):
        grade, score = _detect_index_glossary(_soup('<a href="/glossary">Glossary</a>'), "")
        self.assertEqual(score, 100)

    def test_url_semantic(self):
        grade, score = _url_semantic("https://docs.example.com/nextseq/guide.html")
        self.assertEqual(score, 100)
        grade2, score2 = _url_semantic("https://docs.example.com/?id=123&lang=en")
        self.assertEqual(score2, 20)

    def test_seo_metadata_complete(self):
        html = ('<html lang="en"><head><title>T</title>'
                '<meta name="description" content="d"><link rel="canonical" href="https://e.com/"></head></html>')
        grade, score = _seo_metadata(_soup(html))
        self.assertEqual(score, 100)

    def test_seo_metadata_partial(self):
        grade, score = _seo_metadata(_soup('<html><head><title>T</title></head></html>'))
        self.assertEqual(score, 60)

    def test_findability_html_all_dimensions(self):
        result = analyze_findability("page.html", FULL_TEXT, html=FULL_HTML,
                                     final_url="https://docs.example.com/nextseq/guide.html")
        dims = result["dimensions"]
        for key in ("has_search", "toc_completeness", "has_breadcrumb",
                    "has_index_glossary", "url_semantic", "seo_metadata", "quick_links"):
            self.assertTrue(dims[key]["applicable"], key)
            self.assertIsNotNone(dims[key]["score"], key)

    def test_findability_pdf_na_dimensions(self):
        result = analyze_findability("manual.pdf", FULL_TEXT, pages_text=[FULL_TEXT])
        dims = result["dimensions"]
        for key in ("has_search", "has_breadcrumb", "url_semantic", "seo_metadata", "quick_links"):
            self.assertFalse(dims[key]["applicable"], key)
            self.assertIsNone(dims[key]["score"], key)
        self.assertTrue(dims["toc_completeness"]["applicable"])


class UsabilityTestCase(unittest.TestCase):
    """可用性：任务导向标题/步骤完整性/错误恢复/一致性/链接/祈使句。"""

    TASK_TEXT = """Chapter 1 Installing the System
Chapter 2 Running a Run
Chapter 3 Troubleshooting the Instrument
Chapter 4 Reference
"""
    NON_TASK_TEXT = """Chapter 1 Installation Overview
Chapter 2 Configuration Concept
Chapter 3 System Architecture
Chapter 4 Maintenance Schedule
"""

    def test_task_oriented_headings_high(self):
        grade, score, extra = _task_oriented_headings(self.TASK_TEXT)
        self.assertEqual(score, 100)
        self.assertGreaterEqual(extra["task_ratio"], 0.6)

    def test_task_oriented_headings_low(self):
        grade, score, extra = _task_oriented_headings(self.NON_TASK_TEXT)
        self.assertLessEqual(score, 30)

    def test_task_oriented_zh(self):
        text = "第1章 安装系统\n第2章 配置网络\n第3章 使用仪器\n第4章 维护保养\n"
        grade, score, extra = _task_oriented_headings(text)
        self.assertGreaterEqual(score, 65)

    def test_step_completeness_full(self):
        text = ("Before you begin, check requirements.\n"
                "1) Place the unit.\n2) Connect the power.\n3) Start the system.\n"
                "Expected result: system boots.")
        grade, score, extra = _step_completeness(text)
        self.assertEqual(score, 100)
        self.assertEqual(extra["step_count"], 3)

    def test_step_completeness_missing_prereq(self):
        text = "1) Place the unit.\n2) Connect the power.\n"
        grade, score, extra = _step_completeness(text)
        self.assertEqual(score, 50)

    def test_error_recovery_detected(self):
        grade, score = _detect_error_recovery("See the Troubleshooting chapter for error codes.")
        self.assertEqual(score, 100)

    def test_consistency_mixed_separators(self):
        text = "1) One\n2) Two\n3. Three\n"
        grade, score, extra = _consistency(text)
        self.assertLessEqual(score, 65)
        self.assertTrue(extra.get("issues"))

    def test_consistency_clean(self):
        text = "1) One\n2) Two\n3) Three\n"
        grade, score, _ = _consistency(text)
        self.assertEqual(score, 100)

    def test_imperative_instructions_high(self):
        text = "1) Place the unit.\n2) Connect the power.\n3) Start the system.\n"
        grade, score, extra = _imperative_instructions(text)
        self.assertGreaterEqual(score, 65)
        self.assertEqual(extra["step_lines"], 3)

    def test_imperative_instructions_no_steps(self):
        grade, score, extra = _imperative_instructions("No numbered steps here.")
        self.assertIsNone(score)
        self.assertEqual(extra["step_lines"], 0)

    def test_step_completeness_split_number_merge(self):
        """P1-1 修复：PDF 文本提取把编号与正文拆成两行（'1.' 单独成行）时仍应计数。
        实测 Illumina NextSeq 手册文本层 340 个编号单独成行（占步骤 ~90%），修复前仅计 37。"""
        text = ("Before you begin, check requirements.\n"
                "1.\nPlace the unit.\n"
                "2.\nConnect the power.\n"
                "3.\nStart the system.\n"
                "Expected result: system boots.")
        grade, score, extra = _step_completeness(text)
        self.assertEqual(score, 100)
        self.assertEqual(extra["step_count"], 3)

    def test_step_completeness_mixed_merge_and_inline(self):
        """合并与同行编号混用：两种形态都计入。"""
        text = "1.\nPlace the unit.\n2) Connect the power.\n3.\nStart the system.\n"
        grade, score, extra = _step_completeness(text)
        self.assertEqual(extra["step_count"], 3)

    def test_step_merge_only_for_numbered_alone_lines(self):
        """非编号行不参与合并；编号行后为空行也不合并（不破坏原行结构）。"""
        text = "1.\nPlace the unit.\n\nSome prose here.\n2)\n\n3) Done.\n"
        grade, score, extra = _step_completeness(text)
        self.assertEqual(extra["step_count"], 2)  # "1. Place the unit." + "3) Done."；"2." 后为空行不合并

    def test_imperative_split_number_merge(self):
        """P1-1 修复：可操作指令检测同样受益于编号合并（分母更真实）。"""
        text = "1.\nPlace the unit.\n2.\nConnect the power.\n3.\nStart the system.\n"
        grade, score, extra = _imperative_instructions(text)
        self.assertEqual(extra["step_lines"], 3)
        self.assertEqual(extra["imperative_ratio"], 1.0)
        self.assertGreaterEqual(score, 65)

    def test_step_merge_consecutive_number_lines(self):
        """交叉审查实测：连续编号行（1.\\n2.\\n3.\\n正文）不得互并为假步骤。"""
        text = "1.\n2.\n3.\nPlace the unit.\n"
        grade, score, extra = _step_completeness(text)
        self.assertEqual(extra["step_count"], 1)

    def test_step_merge_title_case_not_merged(self):
        """交叉审查实测：编号后紧跟专名标题（Laser Safety Warning）不合并为步骤。"""
        text = "1.\nLaser Safety Warning\n2.\nPlace the unit.\n"
        grade, score, extra = _step_completeness(text)
        self.assertEqual(extra["step_count"], 1)

    def test_step_three_digit_numbers(self):
        """交叉审查实测：三位数步骤编号（100./101.）应计入（原 \\d{1,2} 系统性漏计）。"""
        text = "100.\nPlace the unit.\n101.\nConnect the power.\n"
        grade, score, extra = _step_completeness(text)
        self.assertEqual(extra["step_count"], 2)
        grade, score, extra = _imperative_instructions(text)
        self.assertEqual(extra["step_lines"], 2)
        self.assertEqual(extra["imperative_ratio"], 1.0)

    def test_usability_html(self):
        result = analyze_usability("page.html", FULL_TEXT, html=FULL_HTML)
        dims = result["dimensions"]
        self.assertIn("task_oriented_headings", dims)
        self.assertIn("step_completeness", dims)
        self.assertIsNotNone(result["overall_score"])


class LinkValidityTestCase(unittest.TestCase):
    def test_link_validity_pdf_with_toc(self):
        """PDF 带书签 → 内部导航可用（不发起网络请求）。"""
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            path = tmp.name
        try:
            import fitz
            doc = fitz.open()
            page = doc.new_page()
            page.insert_text((72, 72), "Installing the system")
            doc.set_toc([[1, "1. Installing the System", 1], [2, "1.1 Overview", 1]])
            doc.save(path)
            doc.close()
            grade, score, extra = _link_validity(path, None, "")
            self.assertEqual(score, 100)
            self.assertGreaterEqual(extra.get("bookmark_count", 0), 1)
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_link_validity_html_no_url_degrade(self):
        grade, score, extra = _link_validity("page.html", _soup(FULL_HTML), "")
        self.assertIsNone(score)  # 无 URL 不发起网络请求，降级不评分


class AggregateAndRenderTestCase(unittest.TestCase):
    def test_experience_entry_three_keys(self):
        result = analyze_experience("page.html", FULL_TEXT, html=FULL_HTML,
                                    final_url="https://docs.example.com/nextseq/guide.html")
        self.assertEqual(set(result.keys()), {"access", "findability", "usability"})
        for part in result.values():
            self.assertIn("overall_score", part)
            self.assertIn("level", part)
            self.assertIn("dimensions", part)
            self.assertIn("notes", part)

    def test_aggregate_na_excluded_from_denominator(self):
        """PDF 输入：3 个 N/A 维度的权重不计入分母，综合评分仍有效。"""
        result = analyze_access("manual.pdf", FULL_TEXT, pages_text=[FULL_TEXT])
        self.assertIsNotNone(result["overall_score"])
        self.assertIn(result["level"], ("excellent", "good", "fair", "poor"))

    def test_report_contains_experience_sections(self):
        from app.utils.competitor_analysis import analyze_tool_usage, analyze_readability
        tool = analyze_tool_usage("page.html", FULL_TEXT, [FULL_TEXT])
        readability = analyze_readability(FULL_TEXT, [FULL_TEXT])
        experience = analyze_experience("page.html", FULL_TEXT, html=FULL_HTML,
                                        final_url="https://docs.example.com/nextseq/guide.html")
        md = render_competitor_report("page.html", tool, readability, experience)
        for title in ("可获得性分析", "易查找性分析", "可用性分析"):
            self.assertIn(title, md, title)
        # 综合评分行已渲染
        self.assertIn("综合评分", md)

    def test_report_backward_compat_without_experience(self):
        from app.utils.competitor_analysis import analyze_tool_usage, analyze_readability
        tool = analyze_tool_usage("page.html", FULL_TEXT, [FULL_TEXT])
        readability = analyze_readability(FULL_TEXT, [FULL_TEXT])
        md = render_competitor_report("page.html", tool, readability)
        self.assertNotIn("可获得性分析", md)

    def test_report_na_rendered(self):
        from app.utils.competitor_analysis import analyze_tool_usage, analyze_readability
        tool = analyze_tool_usage("manual.pdf", FULL_TEXT, [FULL_TEXT])
        readability = analyze_readability(FULL_TEXT, [FULL_TEXT])
        experience = analyze_experience("manual.pdf", FULL_TEXT, pages_text=[FULL_TEXT])
        md = render_competitor_report("manual.pdf", tool, readability, experience)
        # N/A 维度在报告中显示 N/A
        self.assertIn("| 站内搜索 | N/A |", md)


class CrossReviewFixTestCase(unittest.TestCase):
    """交叉审查整改回归：P1 中文标签/检测受限区分/动态编号，P2 同源/层级连续性。"""

    def test_na_notes_uses_chinese_labels(self):
        """P1-①：N/A 说明输出中文维度标签而非英文 key。"""
        # PDF 输入下多个网页属性维度 N/A
        result = analyze_access("manual.pdf", FULL_TEXT, pages_text=[FULL_TEXT])
        notes = result["notes"]
        self.assertTrue(notes)
        joined = "".join(notes)
        for label in ("站内搜索", "移动端适配", "多语言支持"):
            self.assertIn(label, joined, label)
        self.assertNotIn("has_search", joined)
        self.assertNotIn("mobile_adaptation", joined)

    def test_link_validity_local_html_is_restricted_not_na(self):
        """P1-②：本地 HTML 无基础 URL → 检测受限（applicable=True + score=None），
        而非 N/A（不适用于当前输入）。"""
        from app.utils.competitor_experience import _soup
        grade, score, extra = _link_validity("page.html", _soup('<a href="/a.html">A</a>'), "")
        self.assertIsNone(score)
        self.assertFalse(extra.get("na"))
        self.assertIn("检测受限", extra.get("note", ""))

    def test_link_validity_non_html_na(self):
        """P1-②：非 HTML/PDF 输入才标 na=True（真正不适用）。"""
        from app.utils.competitor_experience import _soup
        grade, score, extra = _link_validity("manual.docx", None, "https://docs.example.com/guide.docx")
        self.assertIsNone(score)
        self.assertTrue(extra.get("na"))

    def test_experience_chapter_numbers_follow_structure(self):
        """P1-③：结构统计存在 → 体验章四五六；缺失 → 顺延为三四五。"""
        from app.utils.competitor_analysis import analyze_tool_usage, analyze_readability
        tool = analyze_tool_usage("page.html", FULL_TEXT, [FULL_TEXT])
        tool.pop("structure_stats", None)  # 模拟结构统计缺失
        readability = analyze_readability(FULL_TEXT, [FULL_TEXT])
        experience = analyze_experience("page.html", FULL_TEXT, html=FULL_HTML,
                                        final_url="https://docs.example.com/nextseq/guide.html")
        md = render_competitor_report("page.html", tool, readability, experience)
        self.assertIn("## 三、可获得性分析（Access）", md)
        self.assertIn("## 四、易查找性分析（Findability）", md)
        self.assertIn("## 五、可用性分析（Usability）", md)
        # 结构统计存在时保持四五六（analyze_tool_usage 直调不注入 structure_stats，需手动补）
        tool2 = analyze_tool_usage("page.html", FULL_TEXT, [FULL_TEXT])
        tool2["structure_stats"] = {"page_count": 1, "heading_count": 9, "figure_count": 0,
                                    "table_count": 0, "warning_count": 0}
        md2 = render_competitor_report("page.html", tool2, readability, experience)
        self.assertIn("## 四、可获得性分析（Access）", md2)

    def test_same_site_normalizes_default_port(self):
        """P2-①：同源判定归一化默认端口（example.com 与 example.com:443 同源）。"""
        base = __import__("urllib.parse", fromlist=["urlparse"]).urlparse(
            "https://docs.example.com/guide.html")
        same = __import__("urllib.parse", fromlist=["urlparse"]).urlparse(
            "https://docs.example.com:443/other.html")
        self.assertTrue(_same_site(base, same))
        diff = __import__("urllib.parse", fromlist=["urlparse"]).urlparse(
            "https://docs.example.com:8443/other.html")
        self.assertFalse(_same_site(base, diff))
        other = __import__("urllib.parse", fromlist=["urlparse"]).urlparse(
            "https://other.example.com/guide.html")
        self.assertFalse(_same_site(base, other))

    def test_detect_toc_cross_level_not_full(self):
        """P2-③：跨级标题（h1+h4+h5）不再虚增深度判「完整」。"""
        html = "<html><body><h1>A</h1><h4>D</h4><h5>E</h5></body></html>"
        grade, score, extra = _detect_toc(_soup(html), "", "page.html")
        self.assertEqual(score, 60)  # 层级不连续 → 部分而非完整
        self.assertIn("不连续", extra["note"])

    def test_detect_languages_via_links(self):
        """补测：多语言切换入口（/en/、/zh/）识别。"""
        html = '<html lang="en"><body><a href="/en/">English</a><a href="/zh/">中文</a></body></html>'
        grade, score, n = _detect_languages(_soup(html), html, "")
        self.assertGreaterEqual(n, 2)
        self.assertIn(grade, ("双语", "多语言"))

    def test_detect_quick_links(self):
        """补测：Getting Started 直达入口识别。"""
        grade, score = _detect_quick_links(_soup('<a href="/start">Getting Started</a>'), "")
        self.assertEqual(score, 100)
        grade2, score2 = _detect_quick_links(_soup("<p>plain</p>"), "")
        self.assertEqual(score2, 0)

    def test_aggregate_all_na_returns_none(self):
        """补测：全维度 N/A 时综合评分为 None + insufficient。"""
        dims = {k: {"score": None, "applicable": False} for k in
                ("a", "b", "c", "d")}
        weights = {"a": 0.4, "b": 0.3, "c": 0.2, "d": 0.1}
        overall, level = _aggregate(dims, weights)
        self.assertIsNone(overall)
        self.assertEqual(level, "insufficient")


# ================================================================ 多页聚合（全站递归爬取，V1.2.2）

_PAGE_WITH_BREADCRUMB = """<html><head><title>P1</title></head><body>
<nav aria-label="breadcrumb"><ol><li><a href="/">Home</a></li><li>Topic</li></ol></nav>
<form role="search"><input type="search" name="q"></form>
<h1>Page One</h1><p>page one body text</p></body></html>"""

_PAGE_BARE = """<html><head><title>P2</title></head><body>
<h1>Page Two</h1><p>page two body text</p></body></html>"""

_PAGE_WITH_SEARCH = """<html><head><title>P3</title></head><body>
<form role="search"><input type="search" name="q"></form>
<h1>Page Three</h1><p>page three body text</p></body></html>"""


class MultiPageAggregationTestCase(unittest.TestCase):
    """全站递归爬取场景：结构类维度按「检出页数比例」聚合评分。"""

    def test_half_pages_have_breadcrumb(self):
        exp = analyze_experience(
            "site.html", FULL_TEXT, [FULL_TEXT],
            html=_PAGE_WITH_BREADCRUMB, final_url="https://docs.example.com/",
            pages_html=[_PAGE_WITH_BREADCRUMB, _PAGE_BARE])
        dim = exp["findability"]["dimensions"]["has_breadcrumb"]
        self.assertEqual(dim["score"], 50)          # 1/2 页检出
        self.assertEqual(dim["grade"], "部分检出")
        self.assertIn("1/2 页检出", dim["note"])
        self.assertTrue(dim["applicable"])

    def test_all_pages_have_search(self):
        exp = analyze_experience(
            "site.html", FULL_TEXT, [FULL_TEXT],
            html=_PAGE_WITH_BREADCRUMB, final_url="https://docs.example.com/",
            pages_html=[_PAGE_WITH_BREADCRUMB, _PAGE_WITH_SEARCH])
        dim = exp["findability"]["dimensions"]["has_search"]
        self.assertEqual(dim["score"], 100)
        self.assertEqual(dim["grade"], "普遍检出")
        self.assertIn("2/2 页检出", dim["note"])

    def test_no_pages_have_breadcrumb(self):
        exp = analyze_experience(
            "site.html", FULL_TEXT, [FULL_TEXT],
            html=_PAGE_WITH_BREADCRUMB, final_url="https://docs.example.com/",
            pages_html=[_PAGE_BARE, _PAGE_WITH_SEARCH])
        dim = exp["findability"]["dimensions"]["has_breadcrumb"]
        self.assertEqual(dim["score"], 0)
        self.assertEqual(dim["grade"], "无")

    def test_access_search_aggregated(self):
        exp = analyze_experience(
            "site.html", FULL_TEXT, [FULL_TEXT],
            html=_PAGE_WITH_BREADCRUMB, final_url="https://docs.example.com/",
            pages_html=[_PAGE_WITH_BREADCRUMB, _PAGE_BARE])
        dim = exp["access"]["dimensions"]["has_search"]
        self.assertEqual(dim["score"], 50)
        self.assertIn("1/2 页检出", dim["note"])

    def test_single_page_falls_back_to_single_logic(self):
        """pages_html 只有 1 页（或未提供）：走单页检测逻辑，不聚合。"""
        exp = analyze_experience(
            "site.html", FULL_TEXT, [FULL_TEXT],
            html=_PAGE_WITH_BREADCRUMB, final_url="https://docs.example.com/",
            pages_html=[_PAGE_WITH_BREADCRUMB])
        dim = exp["findability"]["dimensions"]["has_breadcrumb"]
        self.assertEqual(dim["score"], 100)  # 单页检测：有面包屑
        self.assertEqual(dim["grade"], "有")

    def test_usability_unaffected_by_pages_html(self):
        """可用性为内容类维度：pages_html 不改变结果（仍基于合并全文）。"""
        exp = analyze_experience(
            "site.html", FULL_TEXT, [FULL_TEXT],
            html=_PAGE_WITH_BREADCRUMB, final_url="https://docs.example.com/",
            pages_html=[_PAGE_WITH_BREADCRUMB, _PAGE_BARE])
        dim = exp["usability"]["dimensions"]["step_completeness"]
        self.assertEqual(dim["score"], 100)  # FULL_TEXT 含前置条件+预期结果
        self.assertIsNone(exp["usability"].get("error"))

    def test_multilevel_toc_not_inflated_to_full(self):
        """P1 修复：多级评分函数（TOC 20/60/100）聚合用页均得分，不得放大为满分。
        两页均为「部分」TOC（60 分）→ 聚合 60 分而非检出比例放大出的 100 分。"""
        partial_toc = ('<html><head><title>T</title></head><body>'
                       '<h1>A</h1><h2>B</h2><p>body</p></body></html>')
        exp = analyze_experience(
            "site.html", FULL_TEXT, [FULL_TEXT],
            html=partial_toc, final_url="https://docs.example.com/",
            pages_html=[partial_toc, partial_toc])
        dim = exp["findability"]["dimensions"]["toc_completeness"]
        self.assertEqual(dim["score"], 60)
        self.assertEqual(dim["grade"], "部分检出")
        self.assertIn("2/2 页检出", dim["note"])

    def test_login_barrier_strength_preserved(self):
        """P1 修复：登录门槛聚合保留强度——两页均需登录（40 分）聚合 40 分，而非误放大为 100。"""
        login_page = ('<html><head><title>L</title></head><body>'
                      '<form><input type="text" name="u"><input type="password" name="p"></form>'
                      '</body></html>')
        exp = analyze_experience(
            "site.html", FULL_TEXT, [FULL_TEXT],
            html=login_page, final_url="https://docs.example.com/",
            pages_html=[login_page, login_page])
        dim = exp["access"]["dimensions"]["access_barrier"]
        self.assertEqual(dim["score"], 40)
        self.assertIn("2/2 页检出", dim["note"])

    def test_sparse_detection_no_floor_inflation(self):
        """P1 修复：1/21 页检出不再被 20 分下限钳制抬高（极少检出应给低分，而非虚高到 20）。"""
        pages = [_PAGE_BARE] * 20 + [_PAGE_WITH_SEARCH]
        exp = analyze_experience(
            "site.html", FULL_TEXT, [FULL_TEXT] * 21,
            html=_PAGE_BARE, final_url="https://docs.example.com/",
            pages_html=pages)
        dim = exp["findability"]["dimensions"]["has_search"]
        self.assertEqual(dim["score"], 5)  # 页均得分 100/21 ≈ 4.8 → 5（旧实现 max(20, 4.8)=20 虚高）
        self.assertEqual(dim["grade"], "少数检出")
        self.assertIn("1/21 页检出", dim["note"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
