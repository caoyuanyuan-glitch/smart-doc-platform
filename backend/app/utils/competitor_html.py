"""竞品 HTML 文档分析引擎。

职责（对应需求说明书 REQ-DOC-ANALYZE-001 V1.2）：
1. fetch_html：安全抓取远端网页（SSRF 防护：仅公网 http/https、常规端口；
   体积上限；超时控制）。
2. extract_main_text：正文抽取与去噪——剔除 nav/header/footer/aside/script 等
   页面骨架文本，优先取 main/article 正文；识别"JS 渲染受限"的低内容页面。
3. detect_html_tool：HTML 编辑工具识别证据链（MadCap Flare / RoboHelp /
   常见文档站点框架），按">=2 条独立证据 high / 1 条 medium"给置信度。

本模块为纯规则实现，不调用 AI；供 app/api/competitor.py 调用。
"""

from __future__ import annotations

import ipaddress
import re
import socket
from html.parser import HTMLParser
from typing import Dict, List, Optional
from urllib import parse, request

MAX_HTML_BYTES = 5 * 1024 * 1024  # 5 MB
FETCH_TIMEOUT_SECONDS = 20
ALLOWED_PORTS = {80, 443, None}  # None = scheme 默认端口
ALLOWED_CONTENT_TYPES = {"text/html", "application/xhtml+xml", "text/plain"}

USER_AGENT = "SmartDocPlatformCompetitorBot/1.0"

# 正文容器标签：优先从中提取正文
_MAIN_TAGS = {"main", "article"}
# 页面骨架（噪声）标签：其中的文本不参与正文
_BOILERPLATE_TAGS = {"nav", "header", "footer", "aside", "script", "style",
                     "noscript", "form", "svg", "template", "button", "select"}
# 视为换行的块级标签
_BLOCK_TAGS = {"p", "div", "section", "li", "tr", "table", "br", "h1", "h2",
               "h3", "h4", "h5", "h6", "blockquote", "pre", "dd", "dt"} | _MAIN_TAGS

# 低内容判定阈值：正文低于该字符数时，提示"疑似 JS 渲染/骨架页"
LOW_CONTENT_CHARS = 400


class UrlNotAllowedError(ValueError):
    """目标 URL 未通过安全校验（非公网地址/非法端口/非法协议）。"""


def assert_public_http_url(raw_url: str) -> str:
    """校验 URL 为公网 http/https 地址，返回规范化后的 URL。

    防护点：协议白名单、端口白名单、主机解析后禁止环回/私网/保留地址（SSRF）。
    """
    raw = (raw_url or "").strip()
    if not raw:
        raise UrlNotAllowedError("网页链接不能为空")
    parsed = parse.urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise UrlNotAllowedError("仅支持 http/https 网页链接")
    try:
        port = parsed.port
    except ValueError:
        raise UrlNotAllowedError("链接端口不合法")
    if port not in ALLOWED_PORTS:
        raise UrlNotAllowedError("仅支持 80/443 端口")
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise UrlNotAllowedError("链接主机名为空")
    # 先拦截直填 IP 与内网主机名，再做 DNS 解析校验（防解析到内网地址）
    try:
        addr_infos = socket.getaddrinfo(host, port or (443 if parsed.scheme == "https" else 80),
                                        proto=socket.IPPROTO_TCP)
    except OSError as exc:
        raise UrlNotAllowedError(f"主机名解析失败: {host}")
    for info in addr_infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        if not ip.is_global:
            raise UrlNotAllowedError("仅支持公网地址，禁止访问内网/本机链接")
    return raw


def fetch_html(raw_url: str) -> Dict:
    """抓取网页并返回 {html, final_url, content_type, size}。

    校验失败抛 UrlNotAllowedError；抓取/内容问题抛 RuntimeError（由 API 层转 HTTP 状态码）。
    """
    url = assert_public_http_url(raw_url)
    req = request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml;q=0.9,text/plain;q=0.5,*/*;q=0.1",
        },
    )
    try:
        with request.urlopen(req, timeout=FETCH_TIMEOUT_SECONDS) as resp:
            content_type = (resp.headers.get_content_type() or "").lower()
            if content_type not in ALLOWED_CONTENT_TYPES:
                raise RuntimeError(f"链接内容类型不支持: {content_type or 'unknown'}")
            payload = resp.read(MAX_HTML_BYTES + 1)
            if len(payload) > MAX_HTML_BYTES:
                raise RuntimeError("网页内容过大，请换用更短的手册页面")
            charset = resp.headers.get_content_charset() or "utf-8"
            html = payload.decode(charset, errors="replace")
            final_url = resp.geturl() or url
    except UrlNotAllowedError:
        raise
    except RuntimeError:
        raise
    except Exception as exc:  # 网络/超时/编码等统一归为抓取失败
        raise RuntimeError(f"网页抓取失败: {exc}") from exc
    return {"html": html, "final_url": final_url, "content_type": content_type, "size": len(payload)}


class _MainTextExtractor(HTMLParser):
    """HTML 正文抽取器：去噪 + 正文优先 + 资产/框架特征收集。

    - _skip_tags 内的文本全部丢弃（nav/footer/script 等页面骨架）
    - main/article 中的文本单独收集；若正文长度达标（>=LOW_CONTENT_CHARS）
      则以 main/article 为正文，否则回退到全页（已去噪）文本
    - 顺带收集 <title>、meta generator、script/link 资产 URL，供工具识别
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._chunks: List[str] = []
        self._main_chunks: List[str] = []
        self._title_chunks: List[str] = []
        self._skip_depth = 0
        self._main_depth = 0
        self._in_title = False
        self.title = ""
        self.generator = ""
        self.script_srcs: List[str] = []
        self.css_hrefs: List[str] = []
        self.attrs_sample: List[str] = []
        # 结构统计（客观指标）：正文区域的 img / table / h1-h3 标签计数
        self.img_count = 0
        self.table_count = 0
        self.heading_count = 0

    def handle_starttag(self, tag, attrs):
        name = tag.lower()
        # 结构统计：只统计骨架（nav/header/footer 等）之外的内容元素
        if self._skip_depth == 0:
            if name == "img":
                self.img_count += 1
            elif name == "table":
                self.table_count += 1
            elif name in ("h1", "h2", "h3"):
                self.heading_count += 1
        attr_map = {k.lower(): (v or "") for k, v in attrs}
        if name in _BOILERPLATE_TAGS:
            self._skip_depth += 1
            return
        if name == "title":
            self._in_title = True
        if name in _MAIN_TAGS:
            self._main_depth += 1
        if name == "script":
            src = attr_map.get("src", "")
            if src:
                self.script_srcs.append(src)
        if name == "link":
            rel = attr_map.get("rel", "").lower()
            href = attr_map.get("href", "")
            if "stylesheet" in rel and href:
                self.css_hrefs.append(href)
        if name == "meta" and attr_map.get("name", "").lower() == "generator":
            self.generator = attr_map.get("content", "").strip()
        # 收集含工具特征的属性名（如 data-mc-* / data-dita-*）
        for k, v in attrs:
            kl = str(k).lower()
            if (kl.startswith("data-mc") or kl.startswith("data-dita")) and kl not in self.attrs_sample:
                self.attrs_sample.append(kl)
        if name in _BLOCK_TAGS or name in _BOILERPLATE_TAGS:
            self._chunks.append("\n")
            if self._main_depth > 0:
                self._main_chunks.append("\n")

    def handle_endtag(self, tag):
        name = tag.lower()
        if name in _BOILERPLATE_TAGS:
            if self._skip_depth > 0:
                self._skip_depth -= 1
            return
        if name == "title":
            self._in_title = False
        if name in _MAIN_TAGS and self._main_depth > 0:
            self._main_depth -= 1
        if name in _BLOCK_TAGS:
            self._chunks.append("\n")
            if self._main_depth > 0:
                self._main_chunks.append("\n")

    def handle_data(self, data):
        if self._skip_depth > 0:
            return
        text = re.sub(r"\s+", " ", data or "").strip()
        if not text:
            return
        self._chunks.append(text)
        self._chunks.append(" ")
        if self._main_depth > 0:
            self._main_chunks.append(text)
            self._main_chunks.append(" ")
        if self._in_title:
            self._title_chunks.append(text)

    @staticmethod
    def _clean(chunks: List[str]) -> str:
        text = "".join(chunks)
        text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def result(self) -> Dict:
        self.title = re.sub(r"\s+", " ", " ".join(self._title_chunks)).strip()
        page_text = self._clean(self._chunks)
        main_text = self._clean(self._main_chunks)
        low_content = len(main_text) < LOW_CONTENT_CHARS and len(page_text) < LOW_CONTENT_CHARS
        notes = []
        if len(main_text) >= LOW_CONTENT_CHARS:
            full_text = main_text
        else:
            full_text = page_text
            if low_content:
                notes.append(
                    "页面可提取文本过少（可能为 JS 动态渲染或导航骨架页），可读性评分仅供参考；"
                    "如需完整分析，建议在浏览器另存页面后用本地 HTML 上传。"
                )
        return {
            "full_text": full_text,
            "main_text_len": len(main_text),
            "page_text_len": len(page_text),
            "title": self.title,
            "generator": self.generator,
            "script_srcs": self.script_srcs[:30],
            "css_hrefs": self.css_hrefs[:30],
            "attrs_sample": self.attrs_sample[:10],
            "low_content": low_content,
            "notes": notes,
            # 结构统计（客观指标）：剔除骨架后的内容元素计数
            "img_count": self.img_count,
            "table_count": self.table_count,
            "heading_count": self.heading_count,
        }


def extract_main_text(html: str) -> Dict:
    parser = _MainTextExtractor()
    parser.feed(html)
    parser.close()
    return parser.result()


# ------------------------------------------------------------ 工具识别证据链

# (工具名, 类别, 证据规则列表)；每条规则 = (说明, 匹配函数)
def _url_evidence(url: str) -> List[str]:
    evid = []
    path = parse.urlparse(url).path or ""
    if "/Content/" in path:
        evid.append(f"URL 路径含 Flare 导出目录特征 /Content/（{path[:80]}）")
    if "/Skins/" in path:
        evid.append(f"URL 路径含 Flare Skins 目录特征 /Skins/（{path[:80]}）")
    if path.lower().endswith(".htm") and "/Content/" in path:
        evid.append("Topic 页以 .htm 结尾且位于 /Content/ 目录（HAT 导出特征）")
    return evid


def detect_html_tool(final_url: str, extraction: Dict, html: str) -> Dict:
    """基于 URL 特征 / 脚本依赖 / CSS 目录结构 / meta generator 的工具识别。

    置信度：>=2 条独立证据 high；1 条 medium；0 条为未知（low）。
    返回 {tools: [...], evidence: [...], summary}，tools 结构与 PDF 工具识别对齐。
    """
    evidence: List[str] = []
    flare_hits = []
    # --- MadCap Flare（需求一期识别库重点对象）
    flare_hits.extend(_url_evidence(final_url))
    for src in extraction.get("script_srcs") or []:
        low = src.lower()
        if "madcap" in low:
            flare_hits.append(f"脚本依赖含 MadCap 组件: {src[:100]}")
        if "/skins/" in low:
            flare_hits.append(f"脚本位于 Flare Skins 目录: {src[:100]}")
    for href in extraction.get("css_hrefs") or []:
        low = href.lower()
        if "/skins/" in low:
            flare_hits.append(f"样式表位于 Flare Skins 目录: {href[:100]}")
        if "/content/" in low:
            flare_hits.append(f"样式表位于 Flare Content 目录: {href[:100]}")
    if extraction.get("attrs_sample"):
        flare_hits.append("HTML 含 data-mc-* 属性（MadCap 运行时标记）")
    if re.search(r"MadCap\w*\.js|MadCap:", html or ""):
        flare_hits.append("HTML 引用 MadCapAll/MadCap 运行时脚本")

    tools = []
    if flare_hits:
        uniq = list(dict.fromkeys(flare_hits))[:5]
        confidence = "high" if len(uniq) >= 2 else "medium"
        tools.append({
            "name": "MadCap Flare",
            "category": "帮助文档创作工具（HAT）",
            "confidence": confidence,
            "source": "HTML 结构特征（URL/脚本/样式表）",
            "evidence": uniq,
        })
        evidence.extend(uniq)

    # --- Adobe RoboHelp（常见 HAT）
    robo = []
    for src in extraction.get("script_srcs") or []:
        base = src.rsplit("/", 1)[-1].lower()
        if base in {"whutils.js", "whmsg.js", "whver.js", "whstub.js"}:
            robo.append(f"脚本依赖含 RoboHelp WebHelp 组件: {src[:100]}")
    if re.search(r"rgforms?|RoboHelp", html or "", re.IGNORECASE):
        robo.append("HTML 含 RoboHelp 标记")
    if robo:
        tools.append({
            "name": "Adobe RoboHelp",
            "category": "帮助文档创作工具（HAT）",
            "confidence": "high" if len(robo) >= 2 else "medium",
            "source": "HTML 结构特征（脚本依赖）",
            "evidence": robo[:5],
        })
        evidence.extend(robo[:5])

    # --- DITA-OT（结构化写作发布链；评审意见采纳项）
    dita_hits = []
    path_low = (parse.urlparse(final_url).path or "").lower()
    for seg in ("/topics/", "/concepts/", "/tasks/"):
        if seg in path_low:
            dita_hits.append(f"URL 路径含 DITA 输出目录特征 {seg}（{path_low[:80]}）")
    # 负向前瞻排除 "task-list"/"topic-*" 等 GFM 扩展类名（交叉审查 P1-3）
    if re.search(r'class="[^"]*\b(?:topic|concept|task)(?![-\w])', html or ""):
        dita_hits.append("HTML 元素含 DITA topic/concept/task 主题类名")
    if any(a.startswith("data-dita") for a in (extraction.get("attrs_sample") or [])):
        dita_hits.append("HTML 含 data-dita-* 属性（DITA 发布标记）")
    if dita_hits:
        uniq_dita = list(dict.fromkeys(dita_hits))[:5]
        tools.append({
            "name": "DITA-OT",
            "category": "结构化写作/DITA 发布工具",
            "confidence": "high" if len(uniq_dita) >= 2 else "medium",
            "source": "HTML 结构特征（URL/类名/属性）",
            "evidence": uniq_dita,
        })
        evidence.extend(uniq_dita)

    # --- 静态文档框架（generator / 资产特征）
    generator = (extraction.get("generator") or "").strip()
    if generator:
        gen_low = generator.lower()
        framework_map = [
            ("dita", "DITA-OT"),
            ("docusaurus", "Docusaurus"),
            ("vitepress", "VitePress"),
            ("vuepress", "VuePress"),
            ("gitbook", "GitBook"),
            ("sphinx", "Sphinx"),
            ("mkdocs", "MkDocs"),
            ("readme.io", "ReadMe"),
        ]
        for key, name in framework_map:
            if key in gen_low:
                existing = next((t for t in tools if t.get("name") == name), None)
                gen_evidence = f"meta generator: {generator[:80]}"
                if existing:
                    # 结构特征已识别该工具：generator 作为追加证据并入，置信度可升 high
                    if gen_evidence not in existing["evidence"]:
                        existing["evidence"].append(gen_evidence)
                        evidence.append(gen_evidence)
                    if len(existing["evidence"]) >= 2:
                        existing["confidence"] = "high"
                else:
                    tools.append({
                        "name": name,
                        "category": "结构化写作/DITA 发布工具" if name == "DITA-OT" else "文档站点框架",
                        "confidence": "medium",
                        "source": f"meta generator: {generator[:80]}",
                        "evidence": [f"<meta name=generator content 含 {name}>"],
                    })
                    evidence.append(gen_evidence)
                break

    summary = "未能识别明确的编辑工具"
    if tools:
        primary = max(tools, key=lambda t: {"high": 3, "medium": 2, "low": 1}.get(t.get("confidence"), 1))
        summary = f"主编辑工具：{primary['name']}（{primary.get('confidence', '')} 置信，依据 HTML 结构特征）"
    else:
        summary = "未能识别明确的编辑工具（HTML 无已知 HAT/框架特征，证据不足）"

    return {"tools": tools, "evidence": evidence, "summary": summary}
