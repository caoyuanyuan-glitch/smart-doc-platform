"""竞品文档分析引擎（MVP，纯规则实现）。

两个分析能力：
1. 编辑工具识别：读取 PDF 元数据（producer/creator）、嵌入字体与文本指纹，
   推断文档由何种工具制作（InDesign / FrameMaker / Word / LaTeX 等）。
2. 可读性分析：基于统计规则的量化评分，维度包括
   平均句长(25%) / 术语密度(20%) / 被动句比例(20%) / 段落长度(15%) / 修饰词堆叠(20%)。

说明：本模块为 MVP 规则引擎，不调用 AI；语义级增强（如 AI 术语表、语境被动句判断）
预留到 Phase 2，由 app/utils/ai_client.py 统一接入。

当前输出能力：
1. 编辑工具识别
2. 可读性分析
3. 可获得性（Access）/ 易查找性（Findability）/ 可用性（Usability）启发式评分
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------- 语言检测

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def detect_language(full_text: str) -> str:
    """按中文字符占比粗判语言：>=25% 视为中文为主，否则英文为主。"""
    if not full_text:
        return "unknown"
    n_cjk = len(_CJK_RE.findall(full_text))
    ratio = n_cjk / max(len(full_text), 1)
    if ratio >= 0.25:
        return "zh"
    return "en"


# ------------------------------------------------------------ 编辑工具识别

# producer/creator 关键字 -> 工具名（按出现顺序逐个匹配，避免子串误判）
_TOOL_PATTERNS: List[Tuple[str, str, str]] = [
    ("indesign", "Adobe InDesign", "排版工具"),
    ("framemaker", "Adobe FrameMaker", "结构化写作/排版工具"),
    ("frame maker", "Adobe FrameMaker", "结构化写作/排版工具"),
    ("quarkxpress", "QuarkXPress", "排版工具"),
    ("pandoc", "Pandoc", "文档转换工具"),
    ("pdflatex", "LaTeX (pdfTeX)", "排版工具"),
    ("xelatex", "LaTeX (XeTeX)", "排版工具"),
    ("lualatex", "LaTeX (LuaTeX)", "排版工具"),
    ("latex", "LaTeX", "排版工具"),
    ("microsoft", "Microsoft Word", "文字处理工具"),
    ("libreoffice", "LibreOffice Writer", "文字处理工具"),
    ("openoffice", "Apache OpenOffice", "文字处理工具"),
    ("wps", "WPS Office", "文字处理工具"),
    ("distiller", "Adobe Acrobat Distiller", "PDF 转换工具"),
    ("acrobat", "Adobe Acrobat", "PDF 工具"),
    ("pdfium", "PDFium", "浏览器/PDF 渲染内核"),
    ("chrome", "Google Chrome 打印", "浏览器打印"),
    ("edge", "Microsoft Edge 打印", "浏览器打印"),
    ("quartz", "macOS Quartz", "系统打印/排版"),
    ("pages", "Apple Pages", "文字处理工具"),
]

# 字体名关键字 -> 常见宿主工具信号
_FONT_PATTERNS: List[Tuple[str, str]] = [
    ("timesnewroman", "Times New Roman（Word/LaTeX 默认字体）"),
    ("times", "Times 系衬线字体（Word/LaTeX 常用）"),
    ("simsun", "宋体 SimSun（中文 Word 常用）"),
    ("songti", "宋体（中文排版常用）"),
    ("heiti", "黑体（中文排版常用）"),
    ("simhei", "黑体 SimHei（中文 Word 常用）"),
    ("helvetica", "Helvetica（InDesign/通用排版常用）"),
    ("arial", "Arial（Word/通用排版常用）"),
    ("dinpro", "DIN Pro（InDesign 工业风格排版常用）"),
    ("myriadpro", "Myriad Pro（Adobe 系排版常用）"),
    ("minionpro", "Minion Pro（Adobe 系排版常用）"),
    ("sourcehan", "思源黑体 Source Han（InDesign/开源排版常用）"),
    ("noto", "Noto 字体（开源排版/网页常用）"),
    ("cambria", "Cambria（Word 默认衬线字体）"),
    ("calibri", "Calibri（Word 默认字体）"),
]

# 文本指纹：低置信度推测信号
_TEXT_SIGNALS: List[Tuple[re.Pattern, str, str]] = [
    (re.compile(r"\\LaTeX|\\TeX|LaTeX 2e", re.IGNORECASE), "LaTeX", "文档中出现 LaTeX 排版标记"),
    (re.compile(r"[\u00ad]{3,}"), "InDesign 排版", "出现大量软连字符（InDesign 断行特征）"),
    (re.compile(r"[\u201c\u201d\u2018\u2019]{5,}"), "通用文字处理器", "出现密集弯引号（Word/文字处理器特征）"),
]

_WARNING_LINE_RE = re.compile(r"(?im)^\s*(?:warning|caution|danger|notice|警告|注意|危险)\b")
_CHAPTER_LINE_RE = re.compile(r"(?im)^\s*(?:chapter\s+\d+|section\s+\d+|part\s+\d+|第[一二三四五六七八九十0-9]+章)\b")


def _match_producer(producer: str, creator: str) -> List[Dict]:
    """从 PDF 元数据 producer/creator 中匹配已知工具。"""
    haystack = f"{producer} {creator}".lower()
    found = []
    for keyword, name, category in _TOOL_PATTERNS:
        if keyword in haystack:
            if name == "LaTeX" and any(f["name"] != "LaTeX" and "LaTeX" in f["name"] for f in found):
                # 已命中更具体的 LaTeX 变体（pdfTeX/XeTeX/LuaTeX），跳过泛化条目，避免重复展示
                continue
            found.append({"name": name, "category": category})
    return found


def _analyze_fonts(fonts: List[Dict]) -> List[Dict]:
    """根据字体名推断宿主工具信号（仅作佐证）。"""
    signals = []
    seen = set()
    for font in fonts:
        name = str(font.get("name", "") or "")
        ext = str(font.get("ext", "") or "")
        # PyMuPDF get_fonts 的 ext 字段为字体扩展名（Type1/TrueType/OpenType），"n/a" 表示未嵌入
        embedded = bool(ext and ext.lower() != "n/a")
        for keyword, hint in _FONT_PATTERNS:
            if keyword in name.lower() and hint not in seen:
                seen.add(hint)
                signals.append({"name": name, "hint": hint, "embedded": embedded})
                break
    return signals[:6]


def _analyze_text_signals(full_text: str) -> List[Dict]:
    """文本内容指纹（低置信度）。"""
    signals = []
    for pattern, name, desc in _TEXT_SIGNALS:
        if pattern.search(full_text):
            signals.append({"name": name, "desc": desc, "confidence": "low"})
    return signals


def analyze_tool_usage(filepath: str, full_text: str, pages_text: Optional[List[str]] = None) -> Dict:
    """识别文档的编辑/排版工具。

    优先级：PDF 元数据（高置信）> 嵌入字体（中置信）> 文本指纹（低置信，仅推测）。
    返回结构化结果，供 JSON 存储与 Markdown 报告渲染。
    """
    meta = {}
    producer = ""
    creator = ""
    fonts: List[Dict] = []
    format_desc = ""
    n_pages = len(pages_text) if pages_text else 0

    if str(filepath).lower().endswith(".pdf"):
        doc = None
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(filepath)
            meta = dict(doc.metadata or {})
            producer = str(meta.get("producer") or "")
            creator = str(meta.get("creator") or "")
            format_desc = f"PDF {meta.get('format', '')}".strip()
            n_pages = doc.page_count
            seen_fonts = {}
            for page in doc:
                try:
                    for f in page.get_fonts():
                        fname = f[3] if len(f) > 3 else ""  # basefont（字体名）
                        ftype = f[2] if len(f) > 2 else ""   # type（font/3d/type3…）
                        ext = f[1] if len(f) > 1 else ""     # ext（嵌入字体扩展名，"n/a" 未嵌入）
                        key = fname or ftype
                        if key:
                            seen_fonts[key] = {"name": fname or ftype, "type": ftype, "ext": ext}
                except Exception:
                    continue
            fonts = list(seen_fonts.values())
        except Exception as exc:
            print(f"[competitor] fitz 读取元数据失败（降级为文本信号）: {exc}")
        finally:
            if doc is not None:
                try:
                    doc.close()
                except Exception:
                    pass

    tools = _match_producer(producer, creator)
    font_signals = _analyze_fonts(fonts)
    text_signals = _analyze_text_signals(full_text)

    # 置信度标注：元数据命中 -> high；仅字体/文本 -> 降级为 medium/low
    for t in tools:
        t["confidence"] = "high"
        t["source"] = "PDF 元数据 (producer/creator)"
        if t["name"] == "Adobe Acrobat" and not any(t2["name"] != "Adobe Acrobat" for t2 in tools):
            # 仅 Acrobat 而无其他编辑工具时，多半只是"另存为"，置信度降为中
            t["confidence"] = "medium"
            t["source"] = "PDF 元数据 (producer/creator)，疑似仅作保存工具"
    for fs in font_signals:
        if not any(t["name"].lower().split("(")[0].strip() in fs["hint"] for t in tools):
            fs["confidence"] = "medium"
            fs["source"] = f"嵌入字体「{fs['name']}」"

    # 文本信号仅在无任何元数据命中时展示，避免噪声
    if not tools and not font_signals:
        for ts in text_signals:
            ts["source"] = "文本特征指纹"
            tools.append(ts)
    elif text_signals and not tools:
        tools.extend(text_signals)

    # 主工具判断
    summary = "未能识别明确的编辑工具"
    if tools:
        primary = max(tools, key=lambda t: {"high": 3, "medium": 2, "low": 1}.get(t.get("confidence"), 1))
        summary = f"主编辑工具：{primary['name']}（{primary.get('confidence', '')} 置信）"
    elif font_signals:
        summary = f"主编辑工具：未命中元数据，可能为 {font_signals[0]['hint']}（中置信）"

    return {
        "summary": summary,
        "meta": {
            "format": format_desc or (str(filepath).rsplit(".", 1)[-1].upper() if "." in str(filepath) else ""),
            "producer": producer or "",
            "creator": creator or "",
            "title": str(meta.get("title") or ""),
            "pages": n_pages,
        },
        "tools": tools,
        "font_signals": font_signals[:6],
        "text_signals": text_signals,
        "raw_fonts": fonts[:20],
    }


def enrich_tool_usage(tool_analysis: Dict, source_meta: Optional[Dict] = None) -> Dict:
    """基于 HTML 结构线索补强工具识别。"""
    source_meta = source_meta or {}
    meta = dict(tool_analysis.get("meta") or {})
    meta.update({k: v for k, v in source_meta.items() if v not in (None, "")})
    tool_analysis["meta"] = meta

    if str(meta.get("format", "")).upper() != "HTML":
        return tool_analysis

    hints = meta.get("html_hints") or {}
    source_url = str(meta.get("source_url") or "")
    flare_reasons = []
    structural_reasons = []
    if hints.get("content_path") or "/Content/" in source_url:
        structural_reasons.append(f"URL 路径含 Flare 导出目录特征 /Content/（{source_url or 'HTML path'}）")
    if hints.get("topic_htm") or re.search(r"/[^/]+\.htm(?:$|[?#])", source_url, re.IGNORECASE):
        structural_reasons.append("Topic 页以 .htm 结尾且位于 /Content/ 目录（HAT 导出特征）")
    if hints.get("madcap_runtime"):
        flare_reasons.append("HTML 引用 MadCap 运行时脚本或标记")

    all_reasons = flare_reasons + [r for r in structural_reasons if r not in flare_reasons]

    if all_reasons:
        tools = list(tool_analysis.get("tools") or [])
        existing = next((t for t in tools if str(t.get("name")) == "MadCap Flare"), None)
        confidence = "high" if flare_reasons else "medium"
        source = "HTML 运行时与结构特征（脚本/URL/样式表）" if flare_reasons else "HTML 结构特征（URL/样式表）"
        if existing is None:
            tools.insert(0, {
                "name": "MadCap Flare",
                "category": "帮助文档创作工具（HAT）",
                "confidence": confidence,
                "source": source,
                "evidence": all_reasons,
            })
        else:
            existing["confidence"] = confidence
            existing["source"] = source
            existing["evidence"] = all_reasons
        tool_analysis["tools"] = tools
        tool_analysis["summary"] = f"主编辑工具：MadCap Flare（{confidence} 置信）"
        tool_analysis["html_evidence"] = all_reasons
    return tool_analysis


# ------------------------------------------------------------ 可读性分析

_SENT_SPLIT_RE = re.compile(r"[。！？；!?;\n]+")
_EN_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])|(?<=[.!?])\n")
_PASSIVE_ZH_RE = re.compile(r"被|受到|予以|得到.{0,6}(处理|确认|验证|测试)|由.{0,8}(完成|执行|实现|提供)")
_PASSIVE_EN_RE = re.compile(r"\b(?:is|are|was|were|been|being)\s+\w+(?:ed|en)\b|\bby\s+the\b", re.IGNORECASE)
_TERM_TAIL_ZH = re.compile(
    r"(系统|模块|功能|接口|协议|引擎|组件|服务|平台|框架|传感器|芯片|试剂|测序|基因|序列|抗体|仪器|设备|"
    r"装置|参数|配置|规格|认证|标准|规范|文档|手册|流程|机制|策略|算法|模型|数据库|工具|环境|版本|"
    r"程序|软件|硬件|网络|通信|检测|分析|测试|验证|校准|维护|保养|安装|操作|安全|警告|注意|"
    r"电压|电流|温度|压力|转速|分辨率|灵敏度|精度|吞吐量|通量|长度|宽度|高度|重量|容量|功耗|寿命)$"
)
_EN_TERM_RE = re.compile(r"\b[A-Za-z]+(?:-[A-Za-z]+)*\b")
_ALPHANUM_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-\._]*")
_CJK_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]{2,8}")
_MODIFIER_STACK_ZH_RE = re.compile(r"([\u4e00-\u9fff]{1,6}的){3,}")
_MODIFIER_STACK_EN_RE = re.compile(r"\b(?:high|low|fast|slow|new|old|large|small|big|automatic|manual|digital|optical|thermal|electrical|mechanical|advanced|standard|optional|integrated|portable|compact|powerful)\b(?:\s+(?:high|low|fast|slow|new|old|large|small|big|automatic|manual|digital|optical|thermal|electrical|mechanical|advanced|standard|optional|integrated|portable|compact|powerful)){2,}", re.IGNORECASE)

_WEIGHTS = {
    "sentence_length": 0.25,
    "term_density": 0.20,
    "passive_ratio": 0.20,
    "paragraph_length": 0.15,
    "modifier_stack": 0.20,
}


def _clamp_score(score: float) -> float:
    return max(0.0, min(100.0, round(score, 1)))


def _find_page_of(snippet: str, pages_text: List[str]) -> int:
    """在分页文本中定位 snippet 首次出现的页码（1 起），找不到返回 0。"""
    probe = snippet[:40].strip()
    if not probe:
        return 0
    for idx, page in enumerate(pages_text):
        if probe in page:
            return idx + 1
    return 0


def _split_sentences(full_text: str, language: str) -> List[str]:
    if language == "zh":
        parts = _SENT_SPLIT_RE.split(full_text)
    else:
        parts = _EN_SENT_SPLIT_RE.split(full_text)
    return [s.strip() for s in parts if s and len(s.strip()) >= 2]


def _split_paragraphs(full_text: str) -> List[str]:
    parts = re.split(r"\n\s*\n|\n(?=[A-Z\u4e00-\u9fff0-9])", full_text)
    return [p.strip() for p in parts if p and len(p.strip()) >= 5]


def _tokenize(full_text: str, language: str) -> Tuple[List[str], bool]:
    """jieba 分词；不可用时回退字符级 token。返回 (tokens, 是否可用 jieba)。"""
    try:
        import jieba
        if language == "zh":
            tokens = [t for t in jieba.cut(full_text) if t.strip()]
        else:
            tokens = _EN_TERM_RE.findall(full_text.lower())
        return tokens, True
    except Exception:
        if language == "zh":
            tokens = _CJK_TOKEN_RE.findall(full_text)
        else:
            tokens = _EN_TERM_RE.findall(full_text.lower())
        return tokens, False


def _dim_sentence_length(sentences: List[str], language: str, pages_text: List[str]) -> Dict:
    if not sentences:
        return {"score": 100.0, "avg": 0.0, "samples": []}
    if language == "zh":
        lens = [len(s) for s in sentences]
        avg = sum(lens) / len(lens)
        # 中文句长：<=40 字满分，每超 1 字扣 1.5 分
        score = _clamp_score(100 - max(0.0, avg - 40) * 1.5)
        label = f"平均句长 {avg:.1f} 字（建议 ≤ 40 字）"
    else:
        lens = [len(s.split()) for s in sentences]
        avg = sum(lens) / len(lens)
        # 英文句长：<=20 词满分，每超 1 词扣 3 分
        score = _clamp_score(100 - max(0.0, avg - 20) * 3.0)
        label = f"平均句长 {avg:.1f} 词（建议 ≤ 20 词）"
    long_sents = sorted(sentences, key=len, reverse=True)[:3]
    samples = [{"page": _find_page_of(s, pages_text), "text": s[:120]} for s in long_sents]
    return {"score": score, "avg": round(avg, 1), "label": label, "samples": samples}


_STOP_EN = {
    "about", "above", "after", "again", "against", "because", "before", "being",
    "below", "between", "during", "following", "however", "including", "inside",
    "instead", "outside", "should", "through", "within", "without",
}


def _dim_term_density(full_text: str, language: str, tokens: List[str]) -> Dict:
    if not tokens:
        return {"score": 100.0, "density": 0.0, "samples": []}
    if language == "zh":
        # 中文术语信号：含技术后缀（系统/模块/协议…）或含英文/数字的混合词
        term_tokens = [
            t for t in tokens
            if (len(t) >= 2 and _TERM_TAIL_ZH.search(t)) or (_ALPHANUM_TOKEN_RE.fullmatch(t) and re.search(r"[A-Za-z0-9]", t))
        ]
    else:
        term_tokens = [
            t for t in tokens
            if (len(t) > 6 and not t.lower() in _STOP_EN) or re.search(r"\d", t) or "-" in t
        ]
    density = len(term_tokens) / max(len(tokens), 1)
    # 密度 <= 15% 满分；每 +5% 扣 8 分，封顶 100
    score = _clamp_score(100 - max(0.0, density - 0.15) / 0.05 * 8.0)
    samples = [{"page": 0, "text": t} for t in term_tokens[:8]]
    return {
        "score": score,
        "density": round(density * 100, 1),
        "label": f"术语密度 {round(density * 100, 1)}%（建议 ≤ 15%）",
        "samples": samples,
    }


def _dim_passive_ratio(sentences: List[str], language: str, pages_text: List[str]) -> Dict:
    if not sentences:
        return {"score": 100.0, "ratio": 0.0, "samples": []}
    if language == "zh":
        passive_sents = [s for s in sentences if _PASSIVE_ZH_RE.search(s)]
    else:
        passive_sents = [s for s in sentences if _PASSIVE_EN_RE.search(s)]
    ratio = len(passive_sents) / len(sentences)
    # 被动占比 <=10% 满分；每 +5% 扣 10 分
    score = _clamp_score(100 - max(0.0, ratio - 0.10) / 0.05 * 10.0)
    samples = [{"page": _find_page_of(s, pages_text), "text": s[:120]} for s in passive_sents[:3]]
    return {
        "score": score,
        "ratio": round(ratio * 100, 1),
        "label": f"被动句占比 {round(ratio * 100, 1)}%（建议 ≤ 10%）",
        "samples": samples,
    }


def _dim_paragraph_length(paragraphs: List[str], language: str) -> Dict:
    if not paragraphs:
        return {"score": 100.0, "avg": 0.0, "samples": []}
    if language == "zh":
        lens = [len(p) for p in paragraphs]
        avg = sum(lens) / len(lens)
        # 中文段长：<=150 字满分，每超 50 字扣 10 分
        score = _clamp_score(100 - max(0.0, avg - 150) / 50.0 * 10.0)
        label = f"平均段落长度 {avg:.0f} 字（建议 ≤ 150 字）"
    else:
        lens = [len(p.split()) for p in paragraphs]
        avg = sum(lens) / len(lens)
        # 英文段长：<=80 词满分，每超 20 词扣 10 分
        score = _clamp_score(100 - max(0.0, avg - 80) / 20.0 * 10.0)
        label = f"平均段落长度 {avg:.0f} 词（建议 ≤ 80 词）"
    long_paras = sorted(paragraphs, key=len, reverse=True)[:3]
    samples = [{"page": 0, "text": p[:120]} for p in long_paras]
    return {"score": score, "avg": round(avg, 1), "label": label, "samples": samples}


def _dim_modifier_stack(full_text: str, language: str, pages_text: List[str]) -> Dict:
    if language == "zh":
        matches = _MODIFIER_STACK_ZH_RE.findall(full_text)
        hits = [m for m in matches if m][:5]
        count = len(matches)
        score = _clamp_score(100 - count * 4.0)
        label = f"修饰词堆叠出现 {count} 处（如「X 的 X 的 X 的」）"
    else:
        matches = _MODIFIER_STACK_EN_RE.findall(full_text)
        count = len(matches)
        score = _clamp_score(100 - count * 4.0)
        label = f"修饰词堆叠出现 {count} 处（连续 3+ 形容词）"
        hits = [m if isinstance(m, str) else "" for m in matches[:5]]
    samples = [{"page": _find_page_of(h, pages_text) if h else 0, "text": h[:120]} for h in hits]
    return {"score": score, "count": count, "label": label, "samples": samples}


def _level_of(score: float) -> str:
    """综合评分分级（对齐需求说明书 V1.1：excellent/good/fair/poor 四级）。"""
    if score >= 85:
        return "excellent"
    if score >= 70:
        return "good"
    if score >= 55:
        return "fair"
    return "poor"


_VERSION_RE = re.compile(
    r"\b(?:version|ver\.?|revision|rev\.?|document\s+number|doc\s+id|part\s+number)\b|\b\d{4}-\d{2}-\d{2}\b",
    re.IGNORECASE,
)
_TOC_RE = re.compile(r"\b(?:table of contents|contents)\b|\n\s*contents\s*\n", re.IGNORECASE)
_INDEX_RE = re.compile(r"\b(?:index|glossary|terminology)\b", re.IGNORECASE)
_TROUBLE_RE = re.compile(r"\b(?:troubleshooting|faq|error|warning|caution|recovery|resolve)\b", re.IGNORECASE)
_STEP_RE = re.compile(r"(?m)^\s*(?:\d+\.|\d+\)|step\s+\d+|\u2022|-\s+(?:click|select|open|check|review|install|configure|run|restart))", re.IGNORECASE)
_PRECOND_RE = re.compile(r"\b(?:before you begin|prerequisite|requirements|prepare|preparation)\b", re.IGNORECASE)
_TASK_TITLE_RE = re.compile(r"\b(?:install|configure|set up|prepare|run|start|stop|restart|maintain|troubleshoot|review|replace|check|clean)\b", re.IGNORECASE)
_LINK_RE = re.compile(r"https?://\S+|\b\S+\.(?:html?|pdf)\b", re.IGNORECASE)


def _avg_applicable(scores: List[Optional[float]]) -> float:
    vals = [float(s) for s in scores if s is not None]
    if not vals:
        return 0.0
    return _clamp_score(sum(vals) / len(vals))


def analyze_experience(filepath: str, full_text: str, tool_analysis: Dict, pages_text: Optional[List[str]] = None) -> Dict:
    """启发式评估 Access / Findability / Usability。

    目标是补齐竞品横向比较的结构化维度。
    当前为规则近似值，适合趋势判断与同类样本比较。
    """
    pages_text = pages_text or []
    ext = str(filepath).rsplit(".", 1)[-1].lower() if "." in str(filepath) else ""
    meta = tool_analysis.get("meta") or {}
    text = full_text or ""

    has_version = bool(_VERSION_RE.search(text))
    has_toc = bool(_TOC_RE.search(text))
    has_index = bool(_INDEX_RE.search(text))
    has_trouble = bool(_TROUBLE_RE.search(text))
    step_hits = len(_STEP_RE.findall(text))
    has_precond = bool(_PRECOND_RE.search(text))
    link_hits = len(_LINK_RE.findall(text))

    headings = []
    for line in text.splitlines():
        line = line.strip()
        if 4 <= len(line) <= 80 and not line.endswith("."):
            headings.append(line)
    heading_sample = headings[:30]
    task_title_hits = sum(1 for h in heading_sample if _TASK_TITLE_RE.search(h))
    task_title_score = 30
    if heading_sample:
        task_title_score = _clamp_score(task_title_hits / len(heading_sample) * 100)

    format_choice = 50 if ext in {"pdf", "html", "htm"} else 70
    version_transparency = 100 if has_version else 40
    offline_availability = 100 if ext in {"pdf", "html", "htm", "docx", "md", "markdown", "txt"} else 60
    access_overall = _avg_applicable([format_choice, version_transparency, offline_availability])

    toc_score = 60 if has_toc else (25 if len(pages_text) > 5 else 0)
    index_score = 100 if has_index else 0
    findability_overall = _avg_applicable([toc_score, index_score])

    if step_hits >= 8 and has_precond:
        step_completeness = 85
    elif step_hits >= 3:
        step_completeness = 65
    else:
        step_completeness = 35
    error_recovery = 100 if has_trouble else 40
    information_consistency = 100
    link_effectiveness = 60 if ext in {"html", "htm"} and link_hits > 0 else 30
    actionability = 85 if step_hits >= 8 else (60 if step_hits >= 3 else 30)
    usability_overall = _avg_applicable(
        [task_title_score, step_completeness, error_recovery, information_consistency, link_effectiveness, actionability]
    )

    return {
        "access": {
            "overall_score": access_overall,
            "level": _level_of(access_overall),
            "dimensions": {
                "format_choice": {"score": format_choice, "label": "格式选择"},
                "version_transparency": {"score": version_transparency, "label": "版本透明度"},
                "offline_availability": {"score": offline_availability, "label": "离线可用性"},
            },
            "summary": "离线可用性和版本透明度较好，单一导出格式限制了格式弹性。"
            if ext in {"pdf", "html", "htm"}
            else "版本透明度和离线能力可用，格式弹性取决于源文档体系。",
            "na_dimensions": ["获取门槛", "站内搜索", "移动端适配", "多语言支持"],
        },
        "findability": {
            "overall_score": findability_overall,
            "level": _level_of(findability_overall),
            "dimensions": {
                "toc": {"score": toc_score, "label": "目录（TOC）"},
                "index_or_glossary": {"score": index_score, "label": "索引与术语表"},
            },
            "summary": "目录可作为弱导航信号，术语索引决定查找效率上限。",
            "na_dimensions": ["站内搜索", "面包屑导航", "URL 语义化", "SEO 元数据", "关键内容直达"],
        },
        "usability": {
            "overall_score": usability_overall,
            "level": _level_of(usability_overall),
            "dimensions": {
                "task_oriented_titles": {"score": task_title_score, "label": "任务导向标题"},
                "step_completeness": {"score": step_completeness, "label": "步骤完整性"},
                "error_recovery": {"score": error_recovery, "label": "错误恢复信息"},
                "information_consistency": {"score": information_consistency, "label": "信息一致性"},
                "link_effectiveness": {"score": link_effectiveness, "label": "链接有效性"},
                "actionability": {"score": actionability, "label": "可操作指令"},
            },
            "summary": "任务步骤、恢复信息和导航支持共同决定使用顺畅度。",
            "stats": {
                "step_hits": step_hits,
                "task_title_hits": task_title_hits,
                "heading_count_sampled": len(heading_sample),
                "link_hits": link_hits,
            },
        },
    }


def analyze_readability(full_text: str, pages_text: Optional[List[str]] = None, language: str = None) -> Dict:
    """可读性量化分析。

    维度与权重：平均句长 25% / 术语密度 20% / 被动句比例 20% / 段落长度 15% / 修饰词堆叠 20%。
    每维度输出 0-100 分、样本例句；总分 = 加权和，映射评级。
    """
    pages_text = pages_text or []
    language = language or detect_language(full_text)
    if language == "unknown":
        language = "zh"

    sentences = _split_sentences(full_text, language)
    paragraphs = _split_paragraphs(full_text)
    tokens, jieba_ok = _tokenize(full_text, language)

    dims = {
        "sentence_length": _dim_sentence_length(sentences, language, pages_text),
        "term_density": _dim_term_density(full_text, language, tokens),
        "passive_ratio": _dim_passive_ratio(sentences, language, pages_text),
        "paragraph_length": _dim_paragraph_length(paragraphs, language),
        "modifier_stack": _dim_modifier_stack(full_text, language, pages_text),
    }

    overall = sum(dims[k]["score"] * _WEIGHTS[k] for k in _WEIGHTS)
    overall = _clamp_score(overall)

    suggestions = []
    if dims["sentence_length"]["score"] < 75:
        suggestions.append("存在较多超长句，建议拆分：单句不超过 40 字（中文）/ 20 词（英文）。")
    if dims["passive_ratio"]["score"] < 75:
        suggestions.append("被动句比例偏高，建议改为主动语态，明确执行主体。")
    if dims["term_density"]["score"] < 75:
        suggestions.append("术语密度较高，首次出现处建议给出解释或中英文对照。")
    if dims["paragraph_length"]["score"] < 75:
        suggestions.append("段落过长，建议按单一主题拆分，段首给出主题句。")
    if dims["modifier_stack"]["score"] < 75:
        suggestions.append("存在修饰词堆叠，建议精简定语层级，拆为多句表述。")
    if not suggestions:
        suggestions.append("整体可读性良好，继续保持简洁句式与合理段落结构。")

    return {
        "language": language,
        "overall_score": overall,
        "level": _level_of(overall),
        "dimensions": {
            "sentence_length": dims["sentence_length"],
            "term_density": dims["term_density"],
            "passive_ratio": dims["passive_ratio"],
            "paragraph_length": dims["paragraph_length"],
            "modifier_stack": dims["modifier_stack"],
        },
        "stats": {
            "sentence_count": len(sentences),
            "paragraph_count": len(paragraphs),
            "avg_sentence_len": dims["sentence_length"].get("avg", 0),
            "avg_paragraph_len": dims["paragraph_length"].get("avg", 0),
            "term_density_pct": dims["term_density"].get("density", 0),
            "passive_ratio_pct": dims["passive_ratio"].get("ratio", 0),
            "jieba_available": jieba_ok,
        },
        "suggestions": suggestions,
    }


def analyze_structure_stats(full_text: str, source_meta: Optional[Dict] = None, readability: Optional[Dict] = None) -> Dict:
    """结构统计：章节、图表、安全警告与样本可信度提示。"""
    source_meta = source_meta or {}
    readability = readability or {}
    hints = source_meta.get("html_hints") or {}
    sentence_count = ((readability.get("stats") or {}).get("sentence_count")) or 0
    pages = int(source_meta.get("pages") or 1)
    chapter_count = len(_CHAPTER_LINE_RE.findall(full_text or ""))
    image_count = int(hints.get("img_count") or 0)
    table_count = int(hints.get("table_count") or 0)
    warning_count = len(_WARNING_LINE_RE.findall(full_text or ""))

    cautions = []
    if warning_count == 0:
        cautions.append("安全警告数为 0：检测依赖文本关键词匹配，图标或特殊排版呈现的安全提示可能未被统计，建议人工复核。")
    if sentence_count and sentence_count < 200:
        cautions.append(f"文本样本量有限（{sentence_count} 句），评分仅供参考；建议补充更多正文内容后复核。")

    source_url = str(source_meta.get("source_url") or "")
    if "/FrontPages/" in source_url:
        cautions.append("当前页面路径疑似手册入口页/封面页，非正文内容；建议选择具体子页面分析，或上传完整 HTML 包后分析。")

    return {
        "pages": pages,
        "chapter_count": chapter_count,
        "image_count": image_count,
        "table_count": table_count,
        "warning_count": warning_count,
        "cautions": cautions,
    }


def analyze_document(filepath: str, full_text: str, pages_text: Optional[List[str]] = None) -> Dict:
    """文档总入口：返回结构化竞品分析结果。"""
    tool_analysis = analyze_tool_usage(filepath, full_text, pages_text)
    readability = analyze_readability(full_text, pages_text)
    return {
        "tool_analysis": tool_analysis,
        "readability": readability,
        **analyze_experience(filepath, full_text, tool_analysis, pages_text),
    }
