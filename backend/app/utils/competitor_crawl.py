# -*- coding: utf-8 -*-
"""全站递归爬取引擎：从入口 URL 出发，BFS 抓取同域所有子页面/topic。

用户裁定（2026-08-24）：所有子页面、子 topic 都需要爬取，不只是入口页面。
此前仅分析入口页导致站点体验被系统性低估（如面包屑/搜索/TOC 等结构维度）。

安全设计：
- 入口与每个子链接均经 competitor_html.fetch_html（内部 assert_public_http_url
  SSRF 防护：协议/端口白名单 + DNS 公网地址校验）；
- 仅爬取与入口同 host 的页面，防止爬取范围失控；
- 二进制/资源扩展名与 javascript:/mailto: 等链接不视为子页面。

边界（防失控）：
- max_pages=50（含入口），max_depth=4（入口=1，最多向下 3 层）；
- 页间礼貌延迟 POLITE_DELAY，防对目标站点造成压力。
"""
import time
from collections import deque
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse, urldefrag

from app.utils import competitor_html

MAX_PAGES = 50       # 最多抓取页数（含入口）
MAX_DEPTH = 4        # 入口页 depth=1，最多向下 3 层
POLITE_DELAY = 0.2   # 页间礼貌延迟（秒）

# 明显的二进制/资源/脚本扩展名，不作为子页面入队
_SKIP_EXT = {
    ".pdf", ".zip", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
    ".ico", ".css", ".js", ".mp4", ".mp3", ".woff", ".woff2", ".ttf",
    ".eot", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".csv",
    ".json", ".xml", ".rss", ".atom", ".psd", ".ai", ".exe", ".dmg",
    ".tar", ".gz", ".7z", ".rar", ".iso", ".jsp", ".php", ".aspx", ".asp",
}
_SKIP_HREF_PREFIX = ("javascript:", "mailto:", "tel:", "data:", "ftp:")

# 文本层警告行前缀（与 analyze_structure 口径一致）
_WARNING_PREFIXES = ("WARNING", "CAUTION", "DANGER", "ATTENTION", "警告", "注意", "危险", "小心")


def _norm_key(url: str) -> str:
    """URL 规范化去重键：去 fragment/尾斜杠、host 小写、query 排序。"""
    url, _ = urldefrag(url)
    p = urlparse(url)
    path = (p.path or "").rstrip("/") or "/"
    query = p.query
    if query:
        query = "&".join(sorted(query.split("&")))
    key = f"{p.scheme}://{(p.hostname or '').lower()}{path}"
    return key + (f"?{query}" if query else "")


def _is_doc_link(href: str, base_url: str, base_host: str) -> Optional[str]:
    """判断 href 是否为同域文档子页面，是则返回原始绝对 URL，否则 None。

    过滤：非 http/https、跨域、二进制/资源扩展名、脚本式协议。
    """
    raw = (href or "").strip()
    if not raw or raw == "#" or raw.startswith(_SKIP_HREF_PREFIX):
        return None
    full = urljoin(base_url, raw)
    full, _ = urldefrag(full)
    p = urlparse(full)
    if p.scheme not in ("http", "https") or not p.hostname:
        return None
    if p.hostname.lower() != base_host:
        return None  # 仅爬同域
    last_seg = (p.path or "").rsplit("/", 1)[-1]
    if "." in last_seg:
        ext = "." + last_seg.rsplit(".", 1)[-1].lower()
        if ext in _SKIP_EXT:
            return None
    return full


def _count_text_warnings(pages: List[Dict]) -> int:
    """文本层警告行计数（与 analyze_structure 口径一致）。"""
    n = 0
    for p in pages:
        for ln in (p.get("full_text") or "").splitlines():
            s = ln.strip()
            if not s:
                continue
            if s.startswith(_WARNING_PREFIXES) or any(w in s for w in _WARNING_PREFIXES):
                n += 1
    return n


def crawl_site(entry_url: str, max_pages: int = MAX_PAGES, max_depth: int = MAX_DEPTH) -> Dict:
    """从入口 URL 递归爬取同域站点，返回汇总分析所需的页面集合。

    参数:
        entry_url: 用户输入的入口 URL（前首页 / Landing Page / 文档根）
        max_pages: 最多抓取页数（含入口），防止爬取失控
        max_depth: 最大链接深度（入口=1）

    返回:
        entry_url: 用户输入入口
        final_url: 入口页最终 URL（重定向后）
        pages: [{url, depth, title, full_text, html, img_count, table_count,
                 heading_count, warning_symbol_count}]
        ok / failed / total: 成功正文页 / 抓取失败页 / 访问总页数
        skipped: 被过滤的非文档链接数
        dedup: 已访问去重命中数
        combined_text: 非空正文合并（用于可读性/结构/可用性分析）
        structure: 全站累加结构统计（img/table/heading/warning 计数）

    异常: 入口校验失败抛 UrlNotAllowedError；入口抓取失败抛 RuntimeError
          （均由 API 层转 HTTP 状态码）。
    """
    from bs4 import BeautifulSoup

    # 入口预校验 + 抓取（复用 fetch_html 的 SSRF 防护与超时机制）
    competitor_html.assert_public_http_url(entry_url)
    entry = competitor_html.fetch_html(entry_url)
    base_url = entry["final_url"]
    base_host = (urlparse(base_url).hostname or "").lower()

    pages: List[Dict] = []
    visited = {_norm_key(base_url)}
    queue: deque = deque([(base_url, 1)])
    ok = failed = skipped = dedup = 0

    while queue and len(pages) < max_pages:
        url, depth = queue.popleft()
        try:
            fetched = competitor_html.fetch_html(url)
        except Exception:
            failed += 1
            continue
        extraction = competitor_html.extract_main_text(fetched["html"])
        full_text = extraction.get("full_text", "") or ""
        if full_text and not extraction.get("low_content"):
            ok += 1
        pages.append({
            "url": fetched["final_url"],
            "depth": depth,
            "title": extraction.get("title", ""),
            "full_text": full_text,
            "html": fetched["html"],
            "img_count": extraction.get("img_count", 0) or 0,
            "table_count": extraction.get("table_count", 0) or 0,
            "heading_count": extraction.get("heading_count", 0) or 0,
            "warning_symbol_count": extraction.get("warning_symbol_count", 0) or 0,
        })
        # 达到深度上限或页数上限后不再扩展子链接
        if depth >= max_depth or len(pages) >= max_pages:
            continue
        soup = BeautifulSoup(fetched["html"], "html.parser")
        for a in soup.find_all("a", href=True):
            child = _is_doc_link(a.get("href", ""), fetched["final_url"], base_host)
            if not child:
                skipped += 1
                continue
            key = _norm_key(child)
            if key in visited:
                dedup += 1
                continue
            visited.add(key)
            queue.append((child, depth + 1))
        time.sleep(POLITE_DELAY)

    total = ok + failed
    combined = "\n\n".join(p["full_text"] for p in pages if p["full_text"])
    structure = {
        "img_count": sum(p["img_count"] for p in pages),
        "table_count": sum(p["table_count"] for p in pages),
        "heading_count": sum(p["heading_count"] for p in pages),
        "warning_symbol_count": sum(p["warning_symbol_count"] for p in pages),
        "warning_count": _count_text_warnings(pages),
    }
    return {
        "entry_url": entry_url,
        "final_url": base_url,
        "pages": pages,
        "ok": ok,
        "failed": failed,
        "total": total,
        "skipped": skipped,
        "dedup": dedup,
        "combined_text": combined,
        "structure": structure,
    }
