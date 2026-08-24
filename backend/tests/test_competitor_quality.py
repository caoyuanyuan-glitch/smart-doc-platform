"""竞品分析质量单测：术语命中规则 / 评级抑制 / HTML 正文去噪 / Flare 工具识别。

对应 2026-08-24 对《2000_竞品分析报告》的审核结论：
- 旧英文术语判定（len>6 即术语）把 technical/information 等普通词全部误报，
  术语密度虚高至 48.5%；
- 单项维度失分不传导到综合评级（术语 46.4 分仍评 excellent）；
- HTML 抓取未去噪（nav/footer 混入正文）、无工具识别证据链。
"""

import unittest

from app.utils.competitor_analysis import _is_en_term, analyze_readability
from app.utils.competitor_html import (
    UrlNotAllowedError,
    assert_public_http_url,
    detect_html_tool,
    extract_main_text,
)


class TermDetectionTestCase(unittest.TestCase):
    def test_common_words_are_not_terms(self):
        for word in ("technical", "information", "manual", "document", "operation", "respective", "maintaining"):
            self.assertFalse(_is_en_term(word), f"{word} 不应判定为术语")

    def test_domain_terms_are_terms(self):
        for word in ("sequencing", "reagents", "flowcells", "barcode", "adapter", "metagenomics"):
            self.assertTrue(_is_en_term(word), f"{word} 应判定为术语")

    def test_strong_term_features(self):
        self.assertTrue(_is_en_term("DNA"))       # 全大写缩写
        self.assertTrue(_is_en_term("PCR"))
        self.assertTrue(_is_en_term("Q30"))       # 含数字型号
        self.assertTrue(_is_en_term("RNA-seq"))   # 连字符复合术语

    def test_plain_english_density_is_low(self):
        """普通英文说明文本的术语密度应显著低于旧实现的 48.5%。"""
        text = (
            "All trademarks are the property of their respective owners. "
            "For specific trademark information, refer to the legal page. "
            "Technical information for operating and maintaining the system is "
            "provided in this document for reference only."
        )
        result = analyze_readability(text, [text])
        density = result["dimensions"]["term_density"]["density"]
        self.assertLess(density, 15.0, f"普通文本术语密度应 < 15%，实际 {density}%")
        samples = [s["text"] for s in result["dimensions"]["term_density"]["samples"]]
        self.assertNotIn("technical", [s.lower() for s in samples])


class LevelSuppressionTestCase(unittest.TestCase):
    def test_weakest_dimension_caps_level(self):
        """任一维度 < 55 分时，综合评级必须下调（不允许 46 分维度配 excellent）。"""
        para = "DNA RNA PCR sequencing reagents flowcells barcode adapters library."
        text = "\n".join([para] * 8)
        result = analyze_readability(text, [text])
        self.assertEqual(result["dimensions"]["term_density"]["score"], 0.0)
        self.assertGreaterEqual(result["overall_score"], 55)  # 其他维度拉高总分
        self.assertEqual(result["level"], "poor")             # 但评级被最差维度压制
        self.assertTrue(result.get("level_note"))

    def test_balanced_text_not_suppressed(self):
        text = (
            "The instrument is ready. Check the power cable before use.\n"
            "Close the door and press start. Wait for the run to finish.\n"
            "Open the software and review the report. Save the file to disk.\n"
            "Turn off the lamp. Clean the surface with a soft cloth."
        )
        result = analyze_readability(text, [text])
        self.assertFalse(result.get("level_note"), "均衡文本不应出现评级下调说明")


class HtmlExtractionTestCase(unittest.TestCase):
    def test_boilerplate_removed(self):
        html = """
        <html><head><title>T</title></head><body>
          <nav><a>NAVHOME</a><a>NAVPRODUCT</a></nav>
          <header>HEADERBANNER</header>
          <aside>ASIDELINKS</aside>
          <footer>FOOTERLEGAL</footer>
          <main>
            <p>%s</p>
            <p>%s</p>
          </main>
          <script>SCRIPTCODE()</script>
        </body></html>
        """ % (
            "Configure the sequencing instrument before the first run and review all safety notes. " * 3,
            "Complete the maintenance procedure every month and record the results in the log. " * 3,
        )
        result = extract_main_text(html)
        for noise in ("NAVHOME", "HEADERBANNER", "ASIDELINKS", "FOOTERLEGAL", "SCRIPTCODE"):
            self.assertNotIn(noise, result["full_text"], f"噪声 {noise} 应被剔除")
        self.assertIn("Configure the sequencing instrument", result["full_text"])

    def test_low_content_flagged(self):
        html = "<html><body><main><p>Loading...</p></main></body></html>"
        result = extract_main_text(html)
        self.assertTrue(result["low_content"])
        self.assertTrue(any("过少" in n or "JS" in n for n in result["notes"]))

    def test_flare_detection_high_confidence(self):
        extraction = extract_main_text(
            '<html><head>'
            '<link rel="stylesheet" href="/Skins/Default/Stylesheets/Topic.css">'
            '</head><body data-mc-load-hit="1"><p>body</p>'
            '<script src="/Content/Resources/MadCapAll.js"></script></body></html>'
        )
        detection = detect_html_tool(
            "https://support.example.com/Content/IN/FrontPages/Topic.htm",
            extraction,
            "",
        )
        tools = detection["tools"]
        self.assertTrue(tools)
        self.assertEqual(tools[0]["name"], "MadCap Flare")
        self.assertEqual(tools[0]["confidence"], "high")
        self.assertGreaterEqual(len(detection["evidence"]), 2)

    def test_flare_detection_single_evidence_medium(self):
        extraction = extract_main_text(
            '<html><body><p>body</p></body></html>'
        )
        # 仅 /Content/ 一条证据（.html 结尾不构成 Topic.htm 特征）→ medium
        detection = detect_html_tool(
            "https://support.example.com/Content/IN/Topic.html",
            extraction,
            "",
        )
        tools = detection["tools"]
        self.assertTrue(tools)
        self.assertEqual(tools[0]["confidence"], "medium")

    def test_unknown_page_no_false_positive(self):
        extraction = extract_main_text("<html><body><p>plain page</p></body></html>")
        detection = detect_html_tool("https://example.com/about", extraction, "")
        self.assertEqual(detection["tools"], [])
        self.assertIn("未能识别", detection["summary"])


class SsrfGuardTestCase(unittest.TestCase):
    def test_rejects_loopback_and_private(self):
        for url in ("http://127.0.0.1/x", "http://10.0.0.1/x", "http://192.168.1.1/x",
                    "http://169.254.169.254/latest/meta-data", "http://[::1]/x"):
            with self.assertRaises(UrlNotAllowedError, msg=url):
                assert_public_http_url(url)

    def test_rejects_non_http_scheme_and_port(self):
        with self.assertRaises(UrlNotAllowedError):
            assert_public_http_url("ftp://example.com/a")
        with self.assertRaises(UrlNotAllowedError):
            assert_public_http_url("https://example.com:8080/a")

    def test_rejects_hostname_resolving_to_private(self):
        """DNS 解析到私网地址（DNS rebinding 类）同样拒绝。"""
        import socket
        from unittest.mock import patch
        fake = [(2, 1, 6, "", ("10.1.2.3", 443))]
        with patch.object(socket, "getaddrinfo", return_value=fake):
            with self.assertRaises(UrlNotAllowedError):
                assert_public_http_url("https://internal.example.com/")

    def test_allows_public_host(self):
        import socket
        from unittest.mock import patch
        fake = [(2, 1, 6, "", ("93.184.216.34", 443))]
        with patch.object(socket, "getaddrinfo", return_value=fake):
            url = assert_public_http_url("https://docs.example.com/manual.htm")
        self.assertEqual(url, "https://docs.example.com/manual.htm")


if __name__ == "__main__":
    unittest.main()
