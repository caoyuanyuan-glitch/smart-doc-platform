# -*- coding: utf-8 -*-
"""竞品文档体验维度分析：可获得性（Access）/ 易查找性（Findability）/ 可用性（Usability）。

理论依据：《Developing Quality Technical Information》(Hackos & Stevens, 2nd ed.)
质量特征体系—��"文档好不好，看是否易于 X"：
- Easy to find（易查找：组织 Organization + 可检索 Retrievability）
  → 易查找性 Findability（站内搜索/目录/面包屑/索引/URL 语义/SEO/关键内容直达）
  → 可获得性 Access（获取门槛/格式选择/移动端/多语言/版本/离线——用户"拿到"文档的能力）
- Easy to use（易用：任务导向 Task Orientation，DQTI 强调文档应围绕用户任务组织）
  → 可用性 Usability（任务导向标题/步骤完整性/错误恢复/一致性/链接/可操作指令）

输入差异（需求说明书 V1.2 §3.3-3.5）：
- HTML 输入：全维度可检（自动）；
- PDF 输入：站内搜索/移动端/多语言/URL/SEO 等维度 N/A，输出 applicable=False + score=None，
  notes 注明；可检测维度（格式/版本/离线/目录/索引/任务导向/步骤等）正常评分。
每个适用维度输出定性分级（grade）+ 0-100 评分（score）。
综合评分 = 适用维度加权平均（权重体现 DQTI 优先级：任务导向/获取门槛最重）。
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple
from urllib import parse, request
from urllib.error import HTTPError

from bs4 import BeautifulSoup

from app.utils.competitor_analysis import _is_heading_line, _level_of

# ================================================================ 维度定义与权重

# 维度中文标签（P1 修复：N/A 说明输出中文，而非英文 key）
_DIM_LABELS: Dict[str, str] = {
    # Access
    "access_barrier": "获取门槛",
    "formats": "格式选择",
    "has_search": "站内搜索",
    "mobile_adaptation": "移动端适配",
    "languages": "多语言支持",
    "version_transparency": "版本透明度",
    "offline_available": "离线可用性",
    # Findability
    "toc_completeness": "目录完整性",
    "has_breadcrumb": "面包屑导航",
    "has_index_glossary": "索引与术语表",
    "url_semantic": "URL 语义化",
    "seo_metadata": "SEO 元数据",
    "quick_links": "关键内容直达",
    # Usability
    "task_oriented_headings": "任务导向标题",
    "step_completeness": "步骤完整性",
    "error_recovery": "错误恢复信息",
    "consistency": "信息一致性",
    "link_validity": "链接有效性",
    "imperative_instructions": "可操作指令",
}

# 可获得性 Access（用户能否"拿到"文档）
_ACCESS_WEIGHTS: Dict[str, float] = {
    "access_barrier": 0.20,        # 获取门槛：最重要——拿不到文档其余免谈
    "formats": 0.15,               # 格式选择
    "has_search": 0.15,            # 站内搜索
    "mobile_adaptation": 0.10,     # 移动端适配
    "languages": 0.10,             # 多语言支持
    "version_transparency": 0.15,  # 版本透明度：使用者判断新旧
    "offline_available": 0.15,     # 离线可用性
}

# 易查找性 Findability（用户能否快速"找到"内容，DQTI Easy to find）
_FINDABILITY_WEIGHTS: Dict[str, float] = {
    "has_search": 0.15,
    "toc_completeness": 0.20,      # 目录：找内容的第一入口
    "has_breadcrumb": 0.10,
    "has_index_glossary": 0.15,
    "url_semantic": 0.15,
    "seo_metadata": 0.15,
    "quick_links": 0.10,
}

# 可用性 Usability（用户能否"用"文档完成任务，DQTI Easy to use 任务导向）
_USABILITY_WEIGHTS: Dict[str, float] = {
    "task_oriented_headings": 0.20,  # 任务导向标题：DQTI 核心
    "step_completeness": 0.20,       # 步骤完整性
    "error_recovery": 0.15,          # 错误恢复信息
    "consistency": 0.15,             # 信息一致性
    "link_validity": 0.15,           # 链接有效性
    "imperative_instructions": 0.15, # 可操作指令（祈使句）
}

# ================================================================ 通用小工具

_DOWNLOAD_EXTS = (".pdf", ".docx", ".doc", ".epub", ".zip", ".xlsx", ".pptx")
_LANG_CODES = ("en", "zh", "de", "fr", "es", "it", "ja", "ko", "ru", "pt", "ar")


def _dim(score: Optional[float], grade: Optional[str], note: str = "",
         applicable: bool = True, extra: Optional[Dict] = None) -> Dict:
    """构建单维度结果：评分 + 定性分级 + 说明 + 适用性。N/A 时 score/grade 为 None。"""
    d: Dict = {
        "score": score if applicable else None,
        "grade": grade if applicable else None,
        "note": note,
        "applicable": applicable,
    }
    if extra:
        d["extra"] = extra
    return d


def _na_notes(dims: Dict) -> List[str]:
    """收集 N/A 维度说明（需求说明书：PDF 输入下 N/A 维度输出 null 并注明）。
    使用 _DIM_LABELS 输出中文标签；未在映射中的 key 回退原 key。"""
    na = [_DIM_LABELS.get(k, k) for k, d in dims.items() if not d.get("applicable", True)]
    if na:
        return [f"以下维度不适用于当前输入，已置 N/A：{'、'.join(na)}（人工辅助维度可在导出后手动补充）"]
    return []


def _aggregate(dims: Dict, weights: Dict[str, float]) -> Tuple[Optional[float], str]:
    """综合评分 = 适用维度加权平均（N/A 维度权重不计入分母）。"""
    total = 0.0
    wsum = 0.0
    for k, w in weights.items():
        d = dims.get(k) or {}
        if d.get("applicable", True) and isinstance(d.get("score"), (int, float)):
            total += d["score"] * w
            wsum += w
    if wsum <= 0:
        return None, "insufficient"
    return round(total / wsum, 1), _level_of(total / wsum)


def _soup(html: Optional[str]) -> Optional[BeautifulSoup]:
    if not html:
        return None
    try:
        return BeautifulSoup(html, "html.parser")
    except Exception:
        return None


def _page_hit_ratio(pages_html: Optional[List[str]], per_page) -> Optional[Tuple[float, int]]:
    """多页聚合检测（全站递归爬取场景）：对每页 html 执行 per_page(soup) 检测。

    per_page 返回 (grade, score) 或 (grade, score, extra)，score 为该页得分（0-100）。
    返回 (页均得分, 检出页数)；不足 2 页时返回 None（调用方走单页逻辑）。

    交叉审查 P1 修复：聚合用「页均得分」而非「检出比例×100」——
    检出比例对多级评分函数（登录门槛 40/70/100、TOC 20/60/100、SEO 20/60/100、
    移动端 70/100）会把"部分达标"误放大为满分（全站每页 TOC 均 60 分也会得
    "普遍检出 100 分"）。页均得分天然融合覆盖与强度：二值检测（100/0）下
    页均得分 ≡ 检出比例×100，行为与既有契约一致。
    """
    if not pages_html or len(pages_html) < 2:
        return None
    total = 0.0
    hit = 0
    for ph in pages_html:
        soup = _soup(ph)
        if soup is None:
            continue
        try:
            res = per_page(soup)
            score = res[1] if isinstance(res, tuple) and len(res) >= 2 else 0
        except Exception:
            score = 0
        if isinstance(score, (int, float)):
            total += score
        if score and score > 0:
            hit += 1
    return (total / len(pages_html), hit)


def _ratio_grade(avg_score: float) -> Tuple[str, int]:
    """按页均得分映射 (等级, 评分)：普遍达标/部分达标/少数达标/无。"""
    if avg_score >= 80:
        return "普遍检出", round(avg_score)
    if avg_score >= 50:
        return "部分检出", round(avg_score)
    if avg_score > 0:
        return "少数检出", round(avg_score)
    return "无", 0


# ================================================================ Access 检测

def _detect_login_form(soup: BeautifulSoup) -> Tuple[str, int]:
    """获取门槛：无门槛 / 需邮箱 / 需登录账号。"""
    for form in soup.find_all("form"):
        inputs = form.find_all("input")
        has_pass = any((i.get("type") or "").lower() == "password" for i in inputs)
        if has_pass:
            has_user = any((i.get("type") or "").lower() in ("text", "email") for i in inputs)
            return ("需登录账号", 40) if has_user else ("需密码访问", 40)
        emails = [i for i in inputs if (i.get("type") or "").lower() == "email"]
        if emails:
            return "需邮箱", 70
    return "无门槛", 100


def _collect_download_links(soup: BeautifulSoup) -> List[str]:
    """收集页面内下载链接（按后缀判定），去重返回。"""
    found = set()
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip().lower()
        if href.startswith(("javascript:", "mailto:", "tel:", "#")):
            continue
        if any(href.endswith(e) for e in _DOWNLOAD_EXTS):
            found.add(href)
    return sorted(found)


def _detect_mobile(soup: BeautifulSoup, html: str) -> Tuple[str, int]:
    """移动端适配：响应式 / 基础适配 / 无适配。"""
    has_viewport = bool(soup.find("meta", attrs={"name": "viewport"}))
    has_media = "@media" in (html or "")
    if has_viewport and has_media:
        return "响应式", 100
    if has_viewport:
        return "基础适配", 70
    return "无适配", 30


def _detect_languages(soup: BeautifulSoup, html: str, full_text: str) -> Tuple[str, int, int]:
    """多语言支持：统计 lang 属性 + 语言切换入口，返回 (grade, score, 语言数)。"""
    langs = set()
    html_tag = soup.find("html")
    if html_tag and html_tag.get("lang"):
        langs.add(str(html_tag["lang"]).lower().split("-")[0])
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").lower()
        m = re.search(r"/(%s)(/|$|\?)" % "|".join(_LANG_CODES), href)
        if m:
            langs.add(m.group(1))
        m2 = re.search(r"[?&]lang=(%s)\b" % "|".join(_LANG_CODES), href)
        if m2:
            langs.add(m2.group(1))
    sel = soup.find("select")
    if sel:
        for opt in sel.find_all("option"):
            val = (opt.get("value") or opt.get_text() or "").lower().strip()
            if val and len(val) < 12:
                m = re.search(r"\b(%s)\b" % "|".join(_LANG_CODES), val)
                if m:
                    langs.add(m.group(1))
    n = len(langs)
    if n >= 3:
        return "多语言", 100, n
    if n == 2:
        return "双语", 75, n
    if n == 1:
        return "单语言", 40, n
    return "未知", 30, 0


_VERSION_RES = [
    re.compile(r"\bversion\s*[:：]?\s*\d+[\d.]*\b", re.IGNORECASE),
    re.compile(r"\brev(\.|ision)?\s*[:：]?\s*\d", re.IGNORECASE),
    re.compile(r"\b(?:pn|part\s+number|document\s+(?:number|no\.?))\s*[:：]?\s*[\w-]{2,}", re.IGNORECASE),
    re.compile(r"修订日期|版本号|发布日期|修订时间|文档编号|文档版本|ver\.?\s*\d", re.IGNORECASE),
    re.compile(r"\b20\d{2}[-/]\d{1,2}(?:[-/]\d{1,2})?\b"),
]


def _detect_version(full_text: str) -> Tuple[str, int]:
    """版本透明度：版本号 / 修订日期 / 文档编号 / 发布日期。"""
    if any(rx.search(full_text or "") for rx in _VERSION_RES):
        return "有版本标注", 100
    return "未检出", 0


def _detect_search(soup: BeautifulSoup) -> Tuple[str, int]:
    """站内搜索：input[type=search] / form[role=search] / action 含 search。

    扩展（V1.2.2）：MadCap Flare 等 HAT 工具在 <html data-mc-search-type> 声明
    搜索能力（UI 由 JS 注入，静态 DOM 无输入框），识别根属性视为有站内搜索。
    """
    for inp in soup.find_all("input"):
        itype = (inp.get("type") or "").lower()
        name = (inp.get("name") or "").lower()
        if itype == "search" or name in ("q", "search", "query", "keyword", "kw"):
            return "有", 100
    for form in soup.find_all("form"):
        action = (form.get("action") or "").lower()
        role = (form.get("role") or "").lower()
        cls = " ".join(form.get("class") or []).lower()
        if role == "search" or "search" in action or "search" in cls:
            return "有", 100
    html_el = soup.find("html")
    if html_el and (html_el.get("data-mc-search-type") or "").strip():
        return "有（HAT 内置）", 100
    return "无", 0


def analyze_access(filepath: str, full_text: str, pages_text: Optional[List[str]] = None,
                   html: Optional[str] = None, final_url: str = "",
                   pages_html: Optional[List[str]] = None) -> Dict:
    """可获得性（Access）分析：获取门槛与访问体验（需求说明书 §3.3）。

    pages_html（全站递归爬取场景）：结构类维度（登录门槛/格式/搜索/移动端/多语言/离线）
    按「检出页数比例」聚合评分，note 标注 N/M 页检出。
    """
    soup = _soup(html)
    is_html = soup is not None
    dims: Dict = {}

    # 1. 获取门槛（HTML 自动检测；PDF 无登录概念 → N/A 人工辅助）
    if is_html:
        ratio = _page_hit_ratio(pages_html, lambda s: _detect_login_form(s))
        if ratio:
            grade, score = _ratio_grade(ratio[0])
            dims["access_barrier"] = _dim(score, grade, f"登录/注册门槛：{ratio[1]}/{len(pages_html)} 页检出")
        else:
            grade, score = _detect_login_form(soup)
            dims["access_barrier"] = _dim(score, grade, "检测页面登录/注册/邮箱表单")
    else:
        dims["access_barrier"] = _dim(None, None, "PDF 输入无访问门槛概念，需人工辅助确认", applicable=False)

    # 2. 格式选择（PDF：单一格式）
    if is_html:
        dl = _collect_download_links(soup)
        exts = {h.rsplit(".", 1)[-1] for h in dl if "." in h}
        n = len(exts)
        if n >= 3:
            grade, score = "多格式", 100
        elif n == 2:
            grade, score = "双格式", 80
        elif n == 1:
            grade, score = "单一格式", 50
        else:
            grade, score = "仅在线浏览", 30
        dims["formats"] = _dim(score, grade, f"检出下载链接 {len(dl)} 个（格式：{', '.join(sorted(exts)) or '无'}）")
    else:
        dl = None  # PDF 无下载链接集合（P2 修复：离线维度直接复用）
        dims["formats"] = _dim(50, "单一格式", "输入为 PDF 原件（单一格式，本身可离线）")

    # 3. 站内搜索（与 Findability 共享检测逻辑）
    if is_html:
        ratio = _page_hit_ratio(pages_html, lambda s: _detect_search(s))
        if ratio:
            grade, score = _ratio_grade(ratio[0])
            dims["has_search"] = _dim(score, grade, f"站内搜索：{ratio[1]}/{len(pages_html)} 页检出")
        else:
            grade, score = _detect_search(soup)
            dims["has_search"] = _dim(score, grade, "检测 search 输入框/搜索表单")
    else:
        dims["has_search"] = _dim(None, None, "PDF 无站内搜索（N/A）", applicable=False)

    # 4. 移动端适配
    if is_html:
        ratio = _page_hit_ratio(pages_html, lambda s: _detect_mobile(s, s and str(s)))
        if ratio:
            grade, score = _ratio_grade(ratio[0])
            dims["mobile_adaptation"] = _dim(score, grade, f"移动端适配：{ratio[1]}/{len(pages_html)} 页检出")
        else:
            grade, score = _detect_mobile(soup, html or "")
            dims["mobile_adaptation"] = _dim(score, grade, "检测 viewport meta 与媒体查询")
    else:
        dims["mobile_adaptation"] = _dim(None, None, "PDF 无响应式概念（N/A）", applicable=False)

    # 5. 多语言支持
    if is_html:
        ratio = _page_hit_ratio(pages_html, lambda s: _detect_languages(s, str(s), full_text))
        if ratio:
            grade, score = _ratio_grade(ratio[0])
            dims["languages"] = _dim(score, grade, f"多语言支持：{ratio[1]}/{len(pages_html)} 页检出语言标识/切换入口")
        else:
            grade, score, n = _detect_languages(soup, html or "", full_text)
            dims["languages"] = _dim(score, grade, f"检测到 {n} 种语言标识/切换入口")
    else:
        dims["languages"] = _dim(None, None, "PDF 语言不可自动枚举（N/A）", applicable=False)

    # 6. 版本透明度（文本检索）
    grade, score = _detect_version(full_text)
    dims["version_transparency"] = _dim(score, grade, "文本检索版本号/修订日期/文档编号")

    # 7. 离线可用性
    if is_html:
        ratio = _page_hit_ratio(
            pages_html,
            lambda s: (("可下载", 100) if _collect_download_links(s) else ("无", 0)))
        if ratio:
            grade, score = _ratio_grade(ratio[0])
            dims["offline_available"] = _dim(score, grade, f"离线下载入口：{ratio[1]}/{len(pages_html)} 页检出")
        else:
            dims["offline_available"] = _dim(100 if dl else 0, "可下载" if dl else "在线-only",
                                             f"检出 {len(dl)} 个下载链接" if dl else "未检出下载入口")
    else:
        dims["offline_available"] = _dim(100, "可离线", "PDF 原件本身可离线使用")

    overall, level = _aggregate(dims, _ACCESS_WEIGHTS)
    return {"overall_score": overall, "level": level, "dimensions": dims, "notes": _na_notes(dims)}


# ================================================================ Findability 检测

def _detect_toc(soup: Optional[BeautifulSoup], full_text: str, filepath: str) -> Tuple[str, int, Dict]:
    """目录（TOC）完整性：完整 / 部分 / 无。HTML 按大纲层级+导航元素；PDF 按书签/目录页。"""
    if soup is not None:
        has_nav = False
        for tag in soup.find_all(["nav", "ul", "ol"]):
            cls = " ".join(tag.get("class") or []).lower()
            if any(k in cls for k in ("toc", "menu", "tree", "sidenav", "sidebar")):
                has_nav = True
                break
        headings = []
        for htag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            headings += soup.find_all(htag)
        levels = [int(t.name[1]) for t in headings if t.get_text(strip=True)]
        # P2 修复：用「实际出现的不同层级数」而非 max-min+1，跨级标题（h1+h5）不会虚增深度
        distinct = sorted(set(levels))
        depth = len(distinct)
        continuous = bool(distinct) and distinct == list(range(distinct[0], distinct[-1] + 1))
        if has_nav or (depth >= 4 and continuous):
            return "完整", 100, {"note": f"大纲层级 {depth} 层" + (" + 导航/目录元素" if has_nav else "")}
        if depth >= 2:
            note = f"大纲层级 {depth} 层"
            if depth >= 3 and not continuous:
                note += "（层级不连续）"
            return "部分", 60, {"note": note}
        return "无", 20, {"note": "未检出导航/目录结构"}
    if str(filepath or "").lower().endswith(".pdf"):
        try:
            import fitz
            doc = fitz.open(filepath)
            try:
                toc = doc.get_toc()
                max_lvl = max((t[0] for t in toc), default=0)
                if max_lvl >= 2:
                    return "完整（书签）", 100, {"note": f"PDF 书签 {len(toc)} 条（层级 {max_lvl}）"}
                if toc:
                    return "部分（书签）", 60, {"note": f"PDF 书签 {len(toc)} 条"}
                txt = (full_text or "").lower()
                if re.search(r"\b(contents|table of contents)\b", txt) or "目录" in txt:
                    return "部分（目录页）", 60, {"note": "无书签，检出目录页"}
                return "无", 20, {"note": "无书签且未检出目录页"}
            finally:
                doc.close()
        except Exception:
            return "无", 20, {"note": "PDF 书签读取失败"}
    txt = (full_text or "").lower()
    if re.search(r"\b(contents|table of contents)\b", txt) or "目录" in txt:
        return "部分（目录页）", 60, {"note": "检出目录页"}
    return "无", 20, {"note": "未检出目录结构"}


def _detect_breadcrumb(soup: BeautifulSoup) -> Tuple[str, int]:
    """面包屑导航：aria-label=breadcrumb / breadcrumb 类 / nav>ol>li 层级。"""
    for nav in soup.find_all("nav"):
        aria = (nav.get("aria-label") or "").lower()
        cls = " ".join(nav.get("class") or []).lower()
        if "breadcrumb" in aria or "breadcrumb" in cls:
            return "有", 100
        ol = nav.find("ol")
        if ol:
            lis = ol.find_all("li", recursive=False)
            if len(lis) >= 2 and all(li.find("a") or i == len(lis) - 1 for i, li in enumerate(lis)):
                return "有", 100
    if soup.find(class_=re.compile(r"breadcrumb", re.IGNORECASE)):
        return "有", 100
    return "无", 0


def _detect_index_glossary(soup: Optional[BeautifulSoup], full_text: str) -> Tuple[str, int]:
    """索引与术语表：HTML 找链接文本/href；PDF/文本按标题行检测。"""
    if soup is not None:
        for a in soup.find_all("a", href=True):
            text = a.get_text(" ", strip=True).lower()
            href = (a.get("href") or "").lower()
            if any(k in text for k in ("index", "glossary", "索引", "术语表", "词汇表")) or \
               any(k in href for k in ("/index", "/glossary", "index.")):
                return "有", 100
    for ln in (full_text or "").splitlines():
        if _is_heading_line(ln) and re.search(r"(index|glossary)", ln, re.IGNORECASE):
            return "有", 100
        if _is_heading_line(ln) and re.search(r"(索引|术语表|词汇表)", ln):
            return "有", 100
    return "无", 0


def _url_semantic(final_url: str) -> Tuple[str, int]:
    """URL 语义化：路径含可读 slug 且无冗长 query → 语义化；带 query → 半语义；纯参数/数字 → 无意义。"""
    try:
        from urllib.parse import urlparse
        p = urlparse(final_url or "")
        segs = [s for s in p.path.split("/") if s]
        semantic = any(len(s) >= 3 and not s.isdigit() and re.search(r"[a-zA-Z]", s) for s in segs)
        if semantic and not p.query:
            return "语义化", 100
        if semantic and p.query:
            return "半语义", 60
        return "无意义", 20
    except Exception:
        return "无意义", 20


def _seo_metadata(soup: BeautifulSoup) -> Tuple[str, int]:
    """SEO 元数据：title + description + canonical + lang 四项完整性。"""
    has_title = bool(soup.find("title") and soup.find("title").get_text(strip=True))
    has_desc = bool(soup.find("meta", attrs={"name": "description"}))
    has_canonical = bool(soup.find("link", rel="canonical"))
    html_tag = soup.find("html")
    has_lang = bool(html_tag and html_tag.get("lang"))
    present = sum([has_title, has_desc, has_canonical, has_lang])
    if has_title and present >= 3:
        return "完整", 100
    if has_title and present >= 1:
        return "部分", 60
    return "缺失", 20


_QUICK_LINK_RE = re.compile(
    r"(quick\s*(links?|start|reference)|getting\s*started|popular\s*topics|hot\s*topics|"
    r"热门主题|快速开始|常用操作|快速参考|重要信息|常用功能)",
    re.IGNORECASE)


def _detect_quick_links(soup: BeautifulSoup, full_text: str) -> Tuple[str, int]:
    """关键内容直达：Quick links / Getting Started / 热门主题等直达入口。"""
    if soup is not None:
        for a in soup.find_all("a"):
            if _QUICK_LINK_RE.search(a.get_text(" ", strip=True)):
                return "有", 100
        for tag in soup.find_all(class_=re.compile(r"(quick|popular|hot)", re.IGNORECASE)):
            return "有", 100
    if _QUICK_LINK_RE.search(full_text or ""):
        return "有", 100
    return "无", 0


def analyze_findability(filepath: str, full_text: str, pages_text: Optional[List[str]] = None,
                        html: Optional[str] = None, final_url: str = "",
                        pages_html: Optional[List[str]] = None) -> Dict:
    """易查找性（Findability）分析：信息可发现性（需求说明书 §3.4，DQTI Easy to find）。

    pages_html（全站递归爬取场景）：搜索/TOC/面包屑/索引术语表/SEO/直达
    按「检出页数比例」聚合评分；URL 语义化基于入口 URL 单值判定。
    """
    soup = _soup(html)
    is_html = soup is not None
    dims: Dict = {}

    # 1. 站内搜索
    if is_html:
        ratio = _page_hit_ratio(pages_html, lambda s: _detect_search(s))
        if ratio:
            grade, score = _ratio_grade(ratio[0])
            dims["has_search"] = _dim(score, grade, f"站内搜索：{ratio[1]}/{len(pages_html)} 页检出")
        else:
            grade, score = _detect_search(soup)
            dims["has_search"] = _dim(score, grade, "检测 search 输入框/搜索表单")
    else:
        dims["has_search"] = _dim(None, None, "PDF 无站内搜索（N/A）", applicable=False)

    # 2. 目录 TOC
    ratio = _page_hit_ratio(pages_html, lambda s: _detect_toc(s, full_text, filepath))
    if ratio:
        grade, score = _ratio_grade(ratio[0])
        dims["toc_completeness"] = _dim(score, grade, f"目录/导航结构：{ratio[1]}/{len(pages_html)} 页检出")
    else:
        grade, score, extra = _detect_toc(soup, full_text, filepath)
        dims["toc_completeness"] = _dim(score, grade, extra.get("note", "目录/大纲结构检测"), extra=extra)

    # 3. 面包屑导航
    if is_html:
        ratio = _page_hit_ratio(pages_html, lambda s: _detect_breadcrumb(s))
        if ratio:
            grade, score = _ratio_grade(ratio[0])
            dims["has_breadcrumb"] = _dim(score, grade, f"面包屑导航：{ratio[1]}/{len(pages_html)} 页检出")
        else:
            grade, score = _detect_breadcrumb(soup)
            dims["has_breadcrumb"] = _dim(score, grade, "检测面包屑导航")
    else:
        dims["has_breadcrumb"] = _dim(None, None, "PDF 无面包屑（N/A）", applicable=False)

    # 4. 索引与术语表
    ratio = _page_hit_ratio(pages_html, lambda s: _detect_index_glossary(s, full_text))
    if ratio:
        grade, score = _ratio_grade(ratio[0])
        dims["has_index_glossary"] = _dim(score, grade, f"索引/术语表：{ratio[1]}/{len(pages_html)} 页检出")
    else:
        grade, score = _detect_index_glossary(soup, full_text)
        dims["has_index_glossary"] = _dim(score, grade, "检测 Index/Glossary/索引/术语表")

    # 5. URL 语义化（入口 URL 单值判定，不做页级聚合）
    if is_html:
        grade, score = _url_semantic(final_url)
        dims["url_semantic"] = _dim(score, grade, "路径语义化判定（可读 slug vs 参数化路径）")
    else:
        dims["url_semantic"] = _dim(None, None, "PDF 无 URL（N/A）", applicable=False)

    # 6. SEO 元数据
    if is_html:
        ratio = _page_hit_ratio(pages_html, lambda s: _seo_metadata(s))
        if ratio:
            grade, score = _ratio_grade(ratio[0])
            dims["seo_metadata"] = _dim(score, grade, f"SEO 元数据：{ratio[1]}/{len(pages_html)} 页检出")
        else:
            grade, score = _seo_metadata(soup)
            dims["seo_metadata"] = _dim(score, grade, "检测 title/description/canonical/lang 四项")
    else:
        dims["seo_metadata"] = _dim(None, None, "PDF 无 SEO 元数据（N/A）", applicable=False)

    # 7. 关键内容直达
    if is_html:
        ratio = _page_hit_ratio(pages_html, lambda s: _detect_quick_links(s, full_text))
        if ratio:
            grade, score = _ratio_grade(ratio[0])
            dims["quick_links"] = _dim(score, grade, f"关键内容直达：{ratio[1]}/{len(pages_html)} 页检出")
        else:
            grade, score = _detect_quick_links(soup, full_text)
            dims["quick_links"] = _dim(score, grade, "检测 Quick links/热门主题/快速开始入口")
    else:
        dims["quick_links"] = _dim(None, None, "PDF 无首页直达入口概念（N/A）", applicable=False)

    overall, level = _aggregate(dims, _FINDABILITY_WEIGHTS)
    return {"overall_score": overall, "level": level, "dimensions": dims, "notes": _na_notes(dims)}


# ================================================================ Usability 检测

# 任务导向标题：动名词/祈使动词开头（DQTI Task Orientation 核心）。
# 名词形式（Installation/Configuration）不视为任务导向——标题应描述"动作"而非"概念"。
_TASK_HEADING_EN = (
    "installing", "configuring", "setting up", "setting", "using", "starting", "stopping",
    "connecting", "preparing", "cleaning", "maintaining", "replacing", "troubleshooting",
    "updating", "upgrading", "downloading", "uploading", "running", "creating", "managing",
    "monitoring", "calibrating", "transferring", "exporting", "importing", "opening",
    "closing", "enabling", "disabling", "restarting", "shutting down", "powering",
    "testing", "checking", "verifying", "adjusting", "aligning", "loading", "unloading",
    "customizing", "optimizing", "resetting", "filling", "how to",
    "install", "configure", "set up", "use", "start", "stop", "connect", "prepare",
    "clean", "maintain", "replace", "troubleshoot", "update", "upgrade", "download",
    "upload", "run", "create", "manage", "monitor", "calibrate", "transfer", "export",
    "import", "open", "close", "enable", "disable", "restart", "shut down", "power",
    "test", "check", "verify", "adjust", "align", "load", "unload", "customize",
    "optimize", "reset", "fill",
)
_TASK_HEADING_ZH = (
    "安装", "配置", "设置", "使用", "启动", "关闭", "连接", "准备", "清洁", "维护", "更换",
    "故障排除", "更新", "升级", "下载", "上传", "运行", "创建", "管理", "监控", "校准",
    "传输", "导出", "导入", "打开", "启用", "禁用", "重启", "关机", "开机", "测试",
    "检查", "验证", "调整", "对齐", "装载", "卸载", "定制", "优化", "重置", "填充", "如何",
)


def _strip_heading_number(heading: str) -> str:
    """去掉标题行编号前缀（Chapter 5 / 3.2 / 第3章），返回纯标题文本。"""
    return re.sub(
        r"^\s*(?:chapter\s+\d+|appendix\s+[a-z0-9]|\d+(?:\.\d+){1,3}[.、\s]*|"
        r"第[一二三四五六七八九十百\d]+[章节部])[\s:：]*",
        "", heading, flags=re.IGNORECASE).strip()


def _task_oriented_headings(full_text: str) -> Tuple[Optional[str], Optional[int], Dict]:
    """任务导向标题占比：任务动词/动名词开头标题数 / 标题总数。"""
    headings = [ln.strip() for ln in (full_text or "").splitlines() if _is_heading_line(ln)]
    total, task = 0, 0
    for h in headings:
        s = _strip_heading_number(h)
        if not s:
            continue
        total += 1
        low = s.lower()
        if low.startswith(_TASK_HEADING_EN) or low.startswith(_TASK_HEADING_ZH):
            task += 1
    if total == 0:
        return None, None, {"heading_count": 0}
    ratio = task / total
    if ratio >= 0.6:
        return "高", 100, {"task_ratio": round(ratio, 2), "heading_count": total}
    if ratio >= 0.3:
        return "中", 65, {"task_ratio": round(ratio, 2), "heading_count": total}
    return "低", 30, {"task_ratio": round(ratio, 2), "heading_count": total}


_STEP_RE = re.compile(r"^\s*\d{1,3}[.)、]\s+\S")
# PDF 文本提取伪影：编号与正文被拆成两行（"1." 单独一行，正文在下一行）。
# 实测 Illumina NextSeq 手册文本层 340 个编号单独成行，占步骤总量 ~90%（Kimi 外部报告口径 393 吻合）。
_NUMBER_ALONE_RE = re.compile(r"^\s*(\d{1,3}[.)、])\s*$")


def _is_title_case_phrase(line: str) -> bool:
    """近似判断专名/图题标题：≥2 个词且每个词首均为大写字母或数字（如 "Laser Safety Warning"）。

    用于合并守卫：编号后若紧跟专名短语（警告标题/图题），不合并为步骤（避免假步骤）。
    "Place the unit."（the/unit 小写）等真实步骤正文不受影响。
    """
    s = line.strip().rstrip(".")
    words = re.findall(r"[A-Za-z0-9]+(?:[-–][A-Za-z0-9]+)*", s)
    if len(words) < 2 or len(s) > 60:
        return False
    return all(w[0].isupper() or w[0].isdigit() for w in words)


def _merge_split_numbered_lines(text: str) -> str:
    """合并「编号单独成行」与下一行正文，供步骤类检测使用（步骤完整性/可操作指令）。

    例：'1.\\nFrom the control software menu…' → '1. From the control software menu…'
    守卫（避免假步骤，交叉审查实测驱动）：
    - 编号行后为空行 → 不合并（幂等，不影响其他行检测）
    - 下一行仍是编号行（连续编号 `1.\\n2.\\n3.`）→ 不合并，避免 `1. 2.` 假步骤
    - 下一行是专名/图题短语（"Laser Safety Warning"）→ 不合并，避免标题被计为步骤
    """
    if not text:
        return text
    lines = text.split("\n")
    out = []
    i, n = 0, len(lines)
    while i < n:
        ln = lines[i]
        m = _NUMBER_ALONE_RE.match(ln)
        if m and i + 1 < n and lines[i + 1].strip():
            nxt = lines[i + 1]
            if _NUMBER_ALONE_RE.match(nxt) or _is_title_case_phrase(nxt):
                out.append(ln)
                i += 1
                continue
            out.append(m.group(1) + " " + nxt.lstrip())
            i += 2
        else:
            out.append(ln)
            i += 1
    return "\n".join(out)
_PREREQ_RES = [
    re.compile(r"before\s+you\s+begin", re.IGNORECASE),
    re.compile(r"prerequisite", re.IGNORECASE),
    re.compile(r"requirements?\b", re.IGNORECASE),
    re.compile(r"what\s+you\s+need", re.IGNORECASE),
    re.compile(r"前置条件|开始前|前提|准备条件|所需材料|所需物品"),
]
_RESULT_RES = [
    re.compile(r"expected\s+result", re.IGNORECASE),
    re.compile(r"after\s+you\s+(finish|complete|finish)", re.IGNORECASE),
    re.compile(r"what\s+to\s+expect", re.IGNORECASE),
    re.compile(r"预期结果|完成后|完成之后|结果说明|预期效果"),
]


def _step_completeness(full_text: str) -> Tuple[str, int, Dict]:
    """步骤完整性：编号步骤 + 前置条件 + 预期结果（DQTI 任务导向的步骤要素）。"""
    txt = _merge_split_numbered_lines(full_text or "")
    step_count = sum(1 for ln in txt.splitlines() if _STEP_RE.match(ln))
    has_prereq = any(rx.search(txt) for rx in _PREREQ_RES)
    has_result = any(rx.search(txt) for rx in _RESULT_RES)
    if step_count == 0:
        return "缺失", 25, {"step_count": 0}
    if has_prereq and has_result:
        return "完整", 100, {"step_count": step_count, "has_prereq": True, "has_result": True}
    if has_prereq or has_result:
        return "部分", 65, {"step_count": step_count, "has_prereq": has_prereq, "has_result": has_result}
    return "基本", 50, {"step_count": step_count, "has_prereq": False, "has_result": False}


_ERROR_RECOVERY_RES = [
    re.compile(r"troubleshoot", re.IGNORECASE),
    re.compile(r"\bfaq\b", re.IGNORECASE),
    re.compile(r"error\s*codes?", re.IGNORECASE),
    re.compile(r"frequently\s+asked", re.IGNORECASE),
    re.compile(r"故障排除|常见问题|错误码|错误代码|疑难解答|问题排查|错误信息"),
]


def _detect_error_recovery(full_text: str) -> Tuple[str, int]:
    """错误恢复信息：troubleshooting / FAQ / 错误码表等章节。"""
    if any(rx.search(full_text or "") for rx in _ERROR_RECOVERY_RES):
        return "有", 100
    return "无", 0


def _consistency(full_text: str) -> Tuple[str, int, Dict]:
    """信息一致性：标题编号分隔符风格 + 中英文括号使用风格。"""
    txt = full_text or ""
    issues = []
    seps = re.findall(r"^\s*\d{1,3}([.)、])\s+\S", txt, flags=re.M)
    if len(set(seps)) > 1:
        issues.append(f"编号分隔符混用（{'/'.join(sorted(set(seps))) }）")
    half_paren = txt.count("(") + txt.count(")")
    full_paren = txt.count("（") + txt.count("）")
    if half_paren > 5 and full_paren > 5:
        issues.append("中英文括号混用")
    if not issues:
        return "高", 100, {}
    if len(issues) == 1:
        return "中", 65, {"issues": issues}
    return "低", 30, {"issues": issues}


_LINK_CHECK_MAX = 5
_LINK_CHECK_TIMEOUT = 2.0

_DEFAULT_PORTS = {"http": 80, "https": 443}


def _same_site(base: parse.ParseResult, p: parse.ParseResult) -> bool:
    """同源判定（P2 修复）：hostname 相同且端口归一化后一致（默认端口 80/443 视为等价）。"""
    if not base.hostname or not p.hostname:
        return False
    if base.hostname.lower() != p.hostname.lower():
        return False
    bp = base.port or _DEFAULT_PORTS.get(base.scheme, 80)
    pp = p.port or _DEFAULT_PORTS.get(p.scheme, 80)
    return bp == pp


class _NoRedirect(request.HTTPRedirectHandler):
    """SSRF 防护（交叉审查 P0 修复）：不跟随重定向。

    `urlopen` 默认跟随 3xx，重定向目标可能指向内网/私网地址（开放重定向
    二跳 SSRF）。禁止跟随：3xx 由上层捕获并按「链接可达」处理，不产生请求。
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _link_validity(filepath: str, soup: Optional[BeautifulSoup], final_url: str) -> Tuple[Optional[str], Optional[int], Dict]:
    """链接有效性：HTML 抽查站内链接状态码（限 5 条/2s 超时，失败降级）；PDF 检内部书签导航。

    安全（交叉审查 P0 修复）：每条待测链接复用 competitor_html.assert_public_http_url
    做协议/端口/DNS 公网校验，且禁用重定向跟随，防二跳 SSRF。
    """
    if soup is not None:
        if not final_url:
            # 本地 HTML 上传：无基础 URL 无法构建绝对链接，抽查受限而非维度不适用
            return None, None, {"note": "本地 HTML 无基础 URL，未发起链接抽查（检测受限，未评分）"}
        try:
            from app.utils.competitor_html import assert_public_http_url
            base = parse.urlparse(final_url)
            links, seen = [], set()
            for a in soup.find_all("a", href=True):
                href = (a.get("href") or "").strip()
                if not href or href.startswith(("javascript:", "mailto:", "tel:", "#")):
                    continue
                full = parse.urljoin(final_url, href)
                p = parse.urlparse(full)
                if p.scheme not in ("http", "https"):
                    continue
                if p.netloc and not _same_site(base, p):
                    continue  # 只抽查站内链接（P2：hostname+归一化端口同源判定）
                if full in seen:
                    continue
                seen.add(full)
                links.append(full)
                if len(links) >= _LINK_CHECK_MAX:
                    break
            if links:
                dead = 0
                opener = request.build_opener(_NoRedirect)
                for u in links:
                    try:
                        checked = assert_public_http_url(u)  # 协议/端口/DNS 公网校验
                    except Exception:
                        continue  # 不合规链接（内网/私网/非 80-443）跳过，不计死链
                    try:
                        req = request.Request(checked, method="HEAD",
                                              headers={"User-Agent": "SmartDocPlatformCompetitorBot/1.0"})
                        with opener.open(req, timeout=_LINK_CHECK_TIMEOUT) as resp:
                            if resp.status >= 400:
                                dead += 1
                    except HTTPError as exc:
                        if exc.code >= 400:
                            dead += 1  # 3xx（禁跟随）视为链接可达，不计死链
                    except Exception:
                        dead += 1
                rate = dead / len(links)
                if rate == 0:
                    return "优", 100, {"checked": len(links), "dead": dead}
                if rate < 0.05:
                    return "良", 70, {"checked": len(links), "dead": dead}
                return "差", 30, {"checked": len(links), "dead": dead}
        except Exception:
            pass
        return None, None, {"note": "链接抽查失败（网络受限），未评分"}
    if str(filepath or "").lower().endswith(".pdf"):
        try:
            import fitz
            doc = fitz.open(filepath)
            try:
                toc = doc.get_toc()
                if toc:
                    return "有内部导航", 100, {"bookmark_count": len(toc)}
            finally:
                doc.close()
        except Exception:
            pass
        return "无内部导航", 30, {}
    return None, None, {"note": "非 HTML/PDF 输入，链接有效性不适用", "na": True}


_IMPERATIVE_EN = (
    "install", "configure", "set", "use", "start", "stop", "connect", "prepare", "clean",
    "maintain", "replace", "update", "upgrade", "download", "upload", "run", "create",
    "manage", "monitor", "calibrate", "open", "close", "enable", "disable", "restart",
    "test", "check", "verify", "adjust", "align", "load", "unload", "fill", "select",
    "enter", "press", "click", "insert", "remove", "turn", "ensure", "make sure",
    "place", "attach", "detach", "add", "set the", "hold", "push", "pull", "slide",
    "wait", "confirm", "save", "record", "measure", "prepare the",
)
_IMPERATIVE_ZH = (
    "安装", "配置", "设置", "使用", "启动", "关闭", "连接", "准备", "清洁", "维护", "更换",
    "更新", "升级", "下载", "上传", "运行", "创建", "管理", "监控", "校准", "打开", "启用",
    "禁用", "重启", "测试", "检查", "验证", "调整", "对齐", "装载", "卸载", "填充", "选择",
    "输入", "按", "点击", "插入", "移除", "转动", "确保", "放置", "添加", "按住", "按下",
    "推", "拉", "滑动", "等待", "确认", "保存", "记录", "测量", "将",
)


def _imperative_instructions(full_text: str) -> Tuple[Optional[str], Optional[int], Dict]:
    """可操作指令：编号步骤行中以祈使动词开头的占比（无步骤则不评分）。"""
    txt = _merge_split_numbered_lines(full_text or "")
    step_lines = [ln.strip() for ln in txt.splitlines() if _STEP_RE.match(ln)]
    if not step_lines:
        return None, None, {"step_lines": 0, "note": "未检出编号步骤，不评分"}
    imp = 0
    for ln in step_lines:
        body = re.sub(r"^\s*\d{1,3}[.)、]\s*", "", ln)
        low = body.lower()
        if low.startswith(_IMPERATIVE_EN) or body.startswith(_IMPERATIVE_ZH):
            imp += 1
    ratio = imp / len(step_lines)
    if ratio >= 0.6:
        return "高", 100, {"imperative_ratio": round(ratio, 2), "step_lines": len(step_lines)}
    if ratio >= 0.3:
        return "中", 65, {"imperative_ratio": round(ratio, 2), "step_lines": len(step_lines)}
    return "低", 30, {"imperative_ratio": round(ratio, 2), "step_lines": len(step_lines)}


def analyze_usability(filepath: str, full_text: str, pages_text: Optional[List[str]] = None,
                      html: Optional[str] = None, final_url: str = "",
                      pages_html: Optional[List[str]] = None) -> Dict:
    """可用性（Usability）分析：任务导向与使用顺畅度（需求说明书 §3.5，DQTI Easy to use）。

    内容类维度均基于合并后的全站全文（full_text），不做页级聚合；
    pages_html 仅保留接口一致性，链接抽查仍基于入口页（html/final_url）。
    """
    dims: Dict = {}
    soup = _soup(html)

    # 1. 任务导向标题（DQTI 核心）
    grade, score, extra = _task_oriented_headings(full_text)
    if score is None:
        dims["task_oriented_headings"] = _dim(None, None, "未检出标题，无法评估任务导向性", applicable=False)
    else:
        dims["task_oriented_headings"] = _dim(
            score, grade,
            f"任务导向标题占比 {extra.get('task_ratio', 0):.0%}（{extra.get('heading_count', 0)} 个标题）")

    # 2. 步骤完整性
    grade, score, extra = _step_completeness(full_text)
    note = f"编号步骤 {extra.get('step_count', 0)} 个"
    if extra.get("has_prereq"):
        note += "，含前置条件"
    if extra.get("has_result"):
        note += "，含预期结果"
    dims["step_completeness"] = _dim(score, grade, note)

    # 3. 错误恢复信息
    grade, score = _detect_error_recovery(full_text)
    dims["error_recovery"] = _dim(score, grade, "检测 troubleshooting/FAQ/错误码/故障排除章节")

    # 4. 信息一致性
    grade, score, extra = _consistency(full_text)
    note = "未发现明显风格混用" if not extra.get("issues") else "；".join(extra["issues"])
    dims["consistency"] = _dim(score, grade, note, extra=extra if extra else None)

    # 5. 链接有效性（P1 修复：区分「真正 N/A」与「检测受限」——
    #    非 HTML/PDF 输入才 applicable=False；本地 HTML 无 URL/网络受限为检测受限，未评分）
    grade, score, extra = _link_validity(filepath, soup, final_url)
    if score is None:
        dims["link_validity"] = _dim(None, None, extra.get("note", "链接抽查不可用"),
                                     applicable=not bool(extra.get("na")))
    elif extra.get("checked"):
        dims["link_validity"] = _dim(score, grade,
                                     f"抽查 {extra['checked']} 条站内链接，死链 {extra['dead']} 条")
    elif extra.get("bookmark_count"):
        dims["link_validity"] = _dim(score, grade, f"PDF 书签 {extra['bookmark_count']} 条（内部导航）")
    else:
        dims["link_validity"] = _dim(score, grade, "PDF 未检出书签（无内部导航）")

    # 6. 可操作指令
    grade, score, extra = _imperative_instructions(full_text)
    if score is None:
        dims["imperative_instructions"] = _dim(None, None, extra.get("note", "未检出编号步骤，不评分"),
                                               applicable=False)
    else:
        dims["imperative_instructions"] = _dim(
            score, grade,
            f"步骤行祈使句占比 {extra.get('imperative_ratio', 0):.0%}（{extra.get('step_lines', 0)} 个步骤）")

    overall, level = _aggregate(dims, _USABILITY_WEIGHTS)
    return {"overall_score": overall, "level": level, "dimensions": dims, "notes": _na_notes(dims)}


# ================================================================ 总入口

def analyze_experience(filepath: str, full_text: str, pages_text: Optional[List[str]] = None,
                       html: Optional[str] = None, final_url: str = "",
                       pages_html: Optional[List[str]] = None) -> Dict:
    """体验三维度总入口：{access, findability, usability}，每项含 overall_score/level/dimensions/notes。

    pages_html（全站递归爬取场景）：结构类维度按检出页数比例聚合。
    """
    return {
        "access": analyze_access(filepath, full_text, pages_text, html, final_url, pages_html),
        "findability": analyze_findability(filepath, full_text, pages_text, html, final_url, pages_html),
        "usability": analyze_usability(filepath, full_text, pages_text, html, final_url, pages_html),
    }
