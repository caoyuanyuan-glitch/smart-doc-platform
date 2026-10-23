# -*- coding: utf-8 -*-
"""全站递归爬取引擎测试：BFS/去重/同域/上限/深度/失败容错/汇总。

用户裁定（2026-08-24）：所有子页面、子 topic 都需要爬取，不只是入口页面。
"""
import unittest
from unittest import mock

from app.utils import competitor_crawl, competitor_html

# 规范化 URL 键 -> HTML（fetch_html 的 mock 数据）
PAGES = {
    "https://docs.example.com/": (
        "<html><head><title>Home</title></head><body>"
        "<h1>Welcome</h1><p>entry text here</p>"
        "<a href='/guide/install.htm'>Install</a>"
        "<a href='/guide/safety.htm'>Safety</a>"
        "<a href='http://external.example.com/x.htm'>external</a>"
        "<a href='javascript:void(0)'>js</a>"
        "<a href='mailto:a@b.c'>mail</a>"
        "<a href='/manual.pdf'>pdf</a>"
        "</body></html>"
    ),
    "https://docs.example.com/guide/install.htm": (
        "<html><head><title>Install</title></head><body>"
        "<h1>Installing</h1><ol><li>Step one</li><li>Step two</li></ol>"
        "<a href='/guide/install.htm'>self</a>"
        "<a href='/guide/config.htm'>Config</a>"
        "</body></html>"
    ),
    "https://docs.example.com/guide/safety.htm": (
        "<html><head><title>Safety</title></head><body>"
        "<h1>Safety</h1><p>WARNING: keep distance</p>"
        "<a href='/guide/install.htm'>back</a>"
        "</body></html>"
    ),
    "https://docs.example.com/guide/config.htm": (
        "<html><head><title>Config</title></head><body>"
        "<h1>Configuring</h1><p>cfg text</p>"
        "<a href='/guide/deep/a.htm'>deep a</a>"
        "</body></html>"
    ),
    "https://docs.example.com/guide/deep/a.htm": (
        "<html><head><title>Deep A</title></head><body>"
        "<h1>Deep A</h1><p>deep text</p>"
        "<a href='/guide/deep/b.htm'>deep b</a>"
        "</body></html>"
    ),
    "https://docs.example.com/guide/deep/b.htm": (
        "<html><head><title>Deep B</title></head><body>"
        "<h1>Deep B</h1><p>deep text b</p>"
        "</body></html>"
    ),
}


def _mock_fetch(raw_url):
    """mock competitor_html.fetch_html：按规范化键返回假页面；未知页抛 RuntimeError。"""
    key = competitor_crawl._norm_key(raw_url)
    if key not in PAGES:
        raise RuntimeError(f"404 {raw_url}")
    html = PAGES[key]
    # 填充正文到 LOW_CONTENT_CHARS(400) 以上，避免被 low_content 判定拦截
    fill = "<p>" + "lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod. " * 10 + "</p>"
    return {"html": html + fill, "final_url": raw_url, "content_type": "text/html",
            "size": len(html) + len(fill)}


class TestCrawlSite(unittest.TestCase):
    """crawl_site 主流程。"""

    def setUp(self):
        # mock fetch_html（页面数据）与 assert_public_http_url（DNS 校验），
        # 让测试聚焦爬取逻辑；安全校验本身由 fetch_html 单测覆盖
        self.patchers = [
            mock.patch.object(competitor_html, "fetch_html", side_effect=_mock_fetch),
            mock.patch.object(competitor_html, "assert_public_http_url", side_effect=lambda u: u),
        ]
        for p in self.patchers:
            p.start()
            self.addCleanup(p.stop)

    def test_bfs_crawl_all_same_site_pages(self):
        r = competitor_crawl.crawl_site("https://docs.example.com/")
        urls = [p["url"] for p in r["pages"]]
        # 默认 max_depth=4：入口(1) + install/safety(2) + config(3) + deep/a(4) = 5 页
        self.assertEqual(r["ok"], 5)
        self.assertEqual(r["failed"], 0)
        self.assertIn("https://docs.example.com/", urls)
        self.assertIn("https://docs.example.com/guide/install.htm", urls)
        self.assertIn("https://docs.example.com/guide/deep/a.htm", urls)
        # depth 5 的子页不爬（超 max_depth）
        self.assertNotIn("https://docs.example.com/guide/deep/b.htm", urls)
        # 跨域/脚本式/邮件/PDF 链接不入队
        self.assertNotIn("http://external.example.com/x.htm", urls)
        self.assertGreaterEqual(r["skipped"], 4)  # external/js/mail/pdf
        # 重复链接去重（safety -> install，install -> self）
        self.assertGreaterEqual(r["dedup"], 2)

    def test_max_pages_limit(self):
        r = competitor_crawl.crawl_site("https://docs.example.com/", max_pages=2)
        self.assertLessEqual(len(r["pages"]), 2)

    def test_max_depth_limit(self):
        # max_depth=2：只爬入口与直接子页（install/safety），config(depth 3) 不入队
        r = competitor_crawl.crawl_site("https://docs.example.com/", max_depth=2)
        urls = [p["url"] for p in r["pages"]]
        self.assertIn("https://docs.example.com/guide/install.htm", urls)
        self.assertIn("https://docs.example.com/guide/safety.htm", urls)
        self.assertNotIn("https://docs.example.com/guide/config.htm", urls)
        self.assertNotIn("https://docs.example.com/guide/deep/a.htm", urls)

    def test_fetch_failure_tolerated(self):
        # 让 install 页抓取失败：其余页正常，failed 计数
        with mock.patch.object(
            competitor_html, "fetch_html",
            side_effect=lambda u: (_mock_fetch(u) if "install" not in u else (_ for _ in ()).throw(RuntimeError("timeout"))),
        ):
            r = competitor_crawl.crawl_site("https://docs.example.com/")
        urls = [p["url"] for p in r["pages"]]
        # install 失败（其 config 链接随之中断）；safety 的 install 引用被 dedup 拦
        self.assertNotIn("https://docs.example.com/guide/install.htm", urls)
        self.assertEqual(r["failed"], 1)
        self.assertEqual(r["ok"], 2)  # 入口 + safety
        self.assertIn("https://docs.example.com/", urls)
        self.assertIn("https://docs.example.com/guide/safety.htm", urls)

    def test_combined_text_and_structure(self):
        r = competitor_crawl.crawl_site("https://docs.example.com/")
        self.assertIn("entry text here", r["combined_text"])
        self.assertIn("Step one", r["combined_text"])
        self.assertIn("Deep A", r["combined_text"])  # deep/a 已爬取（h1 文本）
        # 结构累加：每页 1 个 h1 → heading_count = 页数；safety 页有 WARNING 行
        self.assertEqual(r["structure"]["heading_count"], len(r["pages"]))
        self.assertGreaterEqual(r["structure"]["warning_count"], 1)

    def test_entry_validation_failure(self):
        # 入口 SSRF 校验失败直接抛 UrlNotAllowedError（不发起请求）
        with mock.patch.object(competitor_html, "assert_public_http_url",
                               side_effect=competitor_html.UrlNotAllowedError("bad")):
            with self.assertRaises(competitor_html.UrlNotAllowedError):
                competitor_crawl.crawl_site("http://127.0.0.1/x.htm")

class TestUrlNormalize(unittest.TestCase):
    """URL 规范化与链接判定。"""

    def test_norm_key_fragment_query_slash(self):
        self.assertEqual(
            competitor_crawl._norm_key("https://Docs.example.com/a/?b=2&a=1#frag"),
            "https://docs.example.com/a?a=1&b=2",
        )
        self.assertEqual(competitor_crawl._norm_key("https://docs.example.com/a/"),
                         competitor_crawl._norm_key("https://docs.example.com/a"))

    def test_is_doc_link_same_site(self):
        self.assertIsNotNone(
            competitor_crawl._is_doc_link("/guide/x.htm", "https://docs.example.com/", "docs.example.com"))
        self.assertIsNone(
            competitor_crawl._is_doc_link("http://other.example.com/x.htm",
                                          "https://docs.example.com/", "docs.example.com"))
        self.assertIsNone(
            competitor_crawl._is_doc_link("javascript:void(0)",
                                          "https://docs.example.com/", "docs.example.com"))
        self.assertIsNone(
            competitor_crawl._is_doc_link("/file.pdf", "https://docs.example.com/", "docs.example.com"))
        self.assertIsNone(competitor_crawl._is_doc_link("#", "https://docs.example.com/", "docs.example.com"))

    def test_is_doc_link_subdomain_treated_cross_site(self):
        # 子域（downloads.example.com）视为跨域，避免爬取范围失控
        self.assertIsNone(
            competitor_crawl._is_doc_link("https://downloads.example.com/x.htm",
                                          "https://docs.example.com/", "docs.example.com"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
