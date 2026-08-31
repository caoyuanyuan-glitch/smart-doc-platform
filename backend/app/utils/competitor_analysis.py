"""竞品文档分析引擎（MVP，纯规则实现）。

三个分析能力：
1. 编辑工具识别：读取 PDF 元数据（producer/creator）、嵌入字体与文本指纹，
   推断文档由何种工具制作（InDesign / FrameMaker / Word / LaTeX 等）。
2. 可读性分析：基于统计规则的量化评分，维度包括
   平均句长(25%) / 术语密度(20%) / 被动句比例(20%) / 段落长度(15%) / 修饰词堆叠(20%)。
3. 结构统计：页数/章节数/图片数/表格数/安全警告数等客观指标（不做主观评分）。

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
    # DITA-OT：producer/creator 常见形态 "DITA Open Toolkit [x.y]" / "dita-ot" / "ditaot"
    # （评审意见采纳项：补齐 DITA 发布链识别，竞品结构化写作主流工具之一）
    ("dita open toolkit", "DITA-OT", "结构化写作/DITA 发布工具"),
    ("dita-ot", "DITA-OT", "结构化写作/DITA 发布工具"),
    ("ditaot", "DITA-OT", "结构化写作/DITA 发布工具"),
    # oXygen XML Editor：DITA 侧最常见的创作工具（creator 字段）
    ("oxygen xml", "oXygen XML Editor", "结构化 XML 编辑器（DITA 常用）"),
    ("pdflatex", "LaTeX (pdfTeX)", "排版工具"),
    ("xelatex", "LaTeX (XeTeX)", "排版工具"),
    ("lualatex", "LaTeX (LuaTeX)", "排版工具"),
    ("latex", "LaTeX", "排版工具"),
    ("microsoft", "Microsoft Word", "文字处理工具"),
    ("libreoffice", "LibreOffice Writer", "文字处理工具"),
    ("openoffice", "Apache OpenOffice", "文字处理工具"),
    ("wps", "WPS Office", "文字处理工具"),
    ("distiller", "Adobe Acrobat Distiller", "PDF 转换工具"),
    ("prince", "Prince XML", "HTML 转 PDF 排版工具"),
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


# 浏览器打印链路的 PDF 导出特征（Producer 关键片段）：出现时工具识别仅代表"打印导出"，
# 原创工具需通过内嵌链接等间接证据反查（外部评审 P1 采纳项）
_BROWSER_PRINT_PRODUCER_MARKS = ("skia/pdf", "chrome", "microsoft edge", "pdfium", "mozillapdf", "webkit")

# PDF 链接反查的最大页数与收集上限（性能保护：浏览器打印导出的手册链接量可能很大）
_PDF_LINK_MAX_PAGES = 50
_PDF_LINK_MAX_SAMPLES = 40

# HAT（帮助创作工具）导出的 PDF 通常保留 HTML 源链接特征：/Content/、/Skins/、.htm topic 等
_HAT_LINK_PATTERNS = [
    re.compile(r"/content/", re.IGNORECASE),
    re.compile(r"/skins/", re.IGNORECASE),
    re.compile(r"\.htm(?:l)?(?:[#?]|$)", re.IGNORECASE),
    re.compile(r"/topics?/", re.IGNORECASE),
]


def _collect_pdf_links(doc, max_pages: int = _PDF_LINK_MAX_PAGES,
                       max_samples: int = _PDF_LINK_MAX_SAMPLES) -> List[str]:
    """收集 PDF 内嵌链接 URL（前 max_pages 页，最多 max_samples 条）。异常静默跳过。"""
    hrefs: List[str] = []
    try:
        for page in doc:
            if len(hrefs) >= max_samples or page.number >= max_pages:
                break
            try:
                for link in page.get_links():
                    uri = str(link.get("uri") or "").strip()
                    if uri and uri not in hrefs:
                        hrefs.append(uri)
                        if len(hrefs) >= max_samples:
                            break
            except Exception:
                continue
    except Exception:
        pass
    return hrefs


def _hat_link_hints(hrefs: List[str]) -> List[str]:
    """分析内嵌链接特征，返回"疑似 HAT 导出"的提示文本（命中才输出，不猜）。"""
    if not hrefs:
        return []
    hits = {}
    for href in hrefs:
        for idx, pat in enumerate(_HAT_LINK_PATTERNS):
            if pat.search(href):
                hits.setdefault(idx, []).append(href[:120])
    if not hits:
        return []
    hints = []
    names = {0: "/Content/", 1: "/Skins/", 2: ".htm/.html topic", 3: "/topics/"}
    for idx in sorted(hits):
        samples = hits[idx][:3]
        hints.append(
            f"内嵌链接 {len(hits[idx])} 条含 {names[idx]} 特征"
            f"（如 {samples[0]!r}），疑似由帮助创作工具（HAT，如 MadCap Flare）导出。"
        )
    return hints


def analyze_tool_usage(filepath: str, full_text: str, pages_text: Optional[List[str]] = None) -> Dict:
    """识别文档的编辑/排版工具。

    优先级：PDF 元数据（高置信）> 嵌入字体（中置信）> 文本指纹（低置信，仅推测）。
    浏���器打印导出的 PDF（Producer 为 Skia/Chrome 等）仅代表打印链路，会额外解析
    内嵌链接反查疑似 HAT 源（外部评审 P1 采纳项）。
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

    # 浏览器打印导出（二手资料）识别与内嵌链接反查（外部评审 P1 采纳项）：
    # producer 命中 Skia/Chrome 等打印链路时，工具识别只代表"打印导出"；若内嵌链接
    # 含 HAT 特征则提示疑似原创工具，并注明可读性统计受分页/断行影响。
    pdf_link_hints: List[str] = []
    is_browser_print = str(producer).lower().startswith(_BROWSER_PRINT_PRODUCER_MARKS) or (
        "chrome" in str(creator).lower() or "edge" in str(creator).lower()
    )
    # 仅浏览器打印 PDF 需要反查（打印链路掩盖了原创工具；正常 PDF 元数据即可识别，
    # 免去二次 fitz.open 的开销——交叉审查 P2 修复）
    if is_browser_print and str(filepath).lower().endswith(".pdf"):
        try:
            import fitz
            _doc = fitz.open(filepath)
            try:
                hrefs = _collect_pdf_links(_doc)
            finally:
                _doc.close()
            pdf_link_hints = _hat_link_hints(hrefs)
        except Exception:
            pdf_link_hints = []

    export_notes: List[str] = []
    if is_browser_print:
        export_notes.append(
            "该 PDF 由浏览器打印导出（Producer 为 Skia/Chrome 等打印链路），"
            "工具识别仅代表打印链路，无法直接确认原创编辑工具；分页与断行为浏览器渲染结果，"
            "句长/段落统计可能受其影响。"
        )
    export_notes.extend(pdf_link_hints)

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
        "export_notes": export_notes,
    }


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

# ---------------------------------------------------------------- 术语库
# 需求 §3.2/§5.3：术语 = 领域专业术语（内置测序/图像分析术语 + 平台词典），
# 而非"长度 > 6 的英文单词"——旧启发式把 technical/information 等普通词全部
# 误判为术语，导致术语密度虚高（实测 48.5%）。命中规则：精确 + 词干（英文）+ 大小写不敏感。
_BUILTIN_EN_TERMS = {
    # 测序领域（需求 §3.2）
    "sequencing", "genomics", "metagenomics", "genome", "genomic", "transcriptome",
    "nucleotide", "oligo", "oligonucleotide", "adapter", "adapters", "ligation",
    "library", "libraries", "flowcell", "flowcells", "cluster", "clusters",
    "basecall", "basecalls", "demultiplexing", "multiplexing", "barcode",
    "barcodes", "indexing", "reads", "read", "run", "chemistry", "reagent",
    "reagents", "kit", "kits", "specimen", "specimens", "assay", "assays",
    "amplification", "denaturation", "hybridization", "polymerase", "primer",
    "primers", "cDNA", "gDNA", "rna", "dna", "dnb", "pcr", "cbs", "wgs",
    "rna-seq", "16s",
    # 图像/信号分析领域（需求 §3.2）
    "segmentation", "threshold", "thresholding", "roi", "rois", "marker",
    "markers", "intensity", "focus", "imaging", "image", "images", "pixel",
    "pixels", "calibration", "align", "alignment", "registration", "contrast",
    "fluorescence", "emission", "excitation", "laser", "optics", "detector",
    # 仪器/运行维护常用技术词
    "instrument", "module", "firmware", "software", "throughput", "yield",
    "q30", "error", "phi", "maintenance", "troubleshooting", "consumable",
    "consumables", "cartridge", "tips", "plate", "tubes", "chamber", "valve",
    "pump", "temperature", "incubation", "wash", "buffer", "buffers",
}

_DIC_DIR = None


# 平台词典中属普通词的条目（拼写白名单用途可保留，术语密度统计需排除）
_PLATFORM_TERM_EXCLUDES = {"table", "figure", "step", "sec", "min", "hr", "rxn", "sativa"}


def _load_platform_terms() -> set:
    """复用平台词典 app/dictionary/technical_terms.txt（测序领域术语）。"""
    global _DIC_DIR
    if _DIC_DIR is None:
        import os
        _DIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dictionary")
    terms = set()
    try:
        path = os.path.join(_DIC_DIR, "technical_terms.txt")
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                term = line.strip().lower()
                if term and not term.startswith("#") and term not in _PLATFORM_TERM_EXCLUDES:
                    terms.add(term)
    except OSError:
        pass  # 词典缺失时降级为仅内置术语
    return terms


def _en_stem(token: str) -> str:
    """轻量英文词干：仅处理规则复数（-s/-es），供词干匹配。"""
    t = token.lower()
    if len(t) > 3 and t.endswith("ies"):
        return t[:-3] + "y"
    if len(t) > 2 and t.endswith("es"):
        return t[:-2]
    if len(t) > 2 and t.endswith("s") and not t.endswith("ss"):
        return t[:-1]
    return t


_ALL_EN_TERMS = _BUILTIN_EN_TERMS | _load_platform_terms()
_ALL_EN_TERMS_STEMS = {_en_stem(t) for t in _ALL_EN_TERMS}


def _is_en_term(raw_token: str) -> bool:
    """英文术语判定：领域术语命中（精确/词干）或强术语特征（数字/连字符/全大写缩写）。"""
    low = raw_token.lower()
    if low in _ALL_EN_TERMS or _en_stem(low) in _ALL_EN_TERMS_STEMS:
        return True
    if re.search(r"\d", raw_token):          # 型号/编号（NextSeq 2000、Q30）
        return True
    if "-" in raw_token:                     # 复合术语（base-call、RNA-seq）
        return True
    if len(raw_token) >= 2 and raw_token.isupper():  # 缩写（DNA、PCR、MGI）
        return True
    return False
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


def _band_score(avg: float, ideal_lo: float, ideal_hi: float,
                k_short: float, k_long: float) -> float:
    """区间制评分（外部评审 P0 采纳项：单向阈值制导致所有达标文档满分、无区分度）。

    理想区间 [ideal_lo, ideal_hi] 内满分；区间外按线性梯度扣分——
    过短/过低（avg < ideal_lo）与过长/过高（avg > ideal_hi）双向扣分，
    避免"电报体句长、过浅术语密度"也拿满分。k_short/k_long 为两侧每单位扣分梯度。
    只扣过高一侧时传 k_short=0.0（配合 avg>=0 语义即不触发短侧扣分）。
    """
    if avg < ideal_lo and k_short > 0:
        return _clamp_score(100.0 - (ideal_lo - avg) * k_short)
    if avg > ideal_hi and k_long > 0:
        return _clamp_score(100.0 - (avg - ideal_hi) * k_long)
    return 100.0


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


_CAPTION_LINE_RES = [
    # 图表题注：Table N / Figure N / 图 N / 表 N（含行尾）
    re.compile(r"^\s*(table|figure|fig\.?|图|表)\s*\d+", re.IGNORECASE),
    # 章节标题：Chapter/Appendix + 编号，或多级编号标题
    re.compile(r"^\s*(chapter|appendix|第[一二三四五六七八九十\d]+[章节部])\b", re.IGNORECASE),
    # 纯规格/单位行：数字 + 单位/括号，无动词（如 "1500 VA LCD 100 V"、"111 cm (43.7 in)"）
    re.compile(r"^\s*\d+[\s\u00a0.]*(?:[A-Za-z]|%|°|×|x|\d)", re.IGNORECASE),
]


def _looks_like_caption_line(line: str) -> bool:
    """判定一行文本是否为标题/图表题注/规格数字行（不应作为"问题例句"展示）。"""
    text = (line or "").strip()
    if not text:
        return True
    if len(text) < 15:
        return True
    return any(pat.match(text) for pat in _CAPTION_LINE_RES)


def _dim_sentence_length(sentences: List[str], language: str, pages_text: List[str]) -> Dict:
    if not sentences:
        return {"score": 100.0, "avg": 0.0, "samples": []}
    if language == "zh":
        lens = [len(s) for s in sentences]
        avg = sum(lens) / len(lens)
        # 中文句长：理想区间 15-40 字（区间制，外部评审 P0 采纳项）
        score = _band_score(avg, 15.0, 40.0, k_short=1.0, k_long=1.5)
        label = f"平均句长 {avg:.1f} 字（理想 15–40 字）"
    else:
        lens = [len(s.split()) for s in sentences]
        avg = sum(lens) / len(lens)
        # 英文句长：理想区间 8-20 词；过短（电报体）与过长均扣分
        score = _band_score(avg, 8.0, 20.0, k_short=2.0, k_long=3.0)
        label = f"平均句长 {avg:.1f} 词（理想 8–20 词）"
    # 长句样本：按长度降序，但过滤标题/图表题注/规格数字行（避免把标题当"问题例句"）
    long_sents = [s for s in sorted(sentences, key=len, reverse=True) if not _looks_like_caption_line(s)][:3]
    if not long_sents:
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
        # 英文：按领域术语库命中（精确/词干/大小写不敏感）+ 强术语特征判定。
        # 注意在原始大小写文本上取词，保留 DNA/PCR 等缩写与 Q30 等型号的大小写信息。
        raw_tokens = _EN_TERM_RE.findall(full_text)
        term_tokens = [t for t in raw_tokens if _is_en_term(t)]
        tokens = raw_tokens
    density = len(term_tokens) / max(len(tokens), 1)
    # 术语密度：理想区间 5%-15%（区间制，外部评审 P0 采纳项）。
    # 过低 = 技术深度不足，过高 = 术语堆砌，均扣分；短侧梯度更缓（轻度惩罚）。
    score = _band_score(density, 0.05, 0.15, k_short=200.0, k_long=160.0)
    # 密术语句子样本（外部评审 P1 采纳项）：按句内术语命中数取 top5，替代"术语词列表"
    term_set = set(term_tokens[:200])
    dense_sents = _dense_term_sentences(full_text, language, term_set, top_n=5)
    samples = [{"page": 0, "text": s[:120]} for s in dense_sents]
    return {
        "score": score,
        "density": round(density * 100, 1),
        "label": f"术语密度 {round(density * 100, 1)}%（理想 5%–15%）",
        "samples": samples,
    }


def _dense_term_sentences(full_text: str, language: str, term_set: set, top_n: int = 5) -> List[str]:
    """找出术语密度最高的句子（术语命中数 >= 3 且占比高），作为"密术语句子"样本。

    外部评审 P1 采纳项：术语维度的问题例句应为句子实例，而非孤立的术语词列表。
    """
    sents = _split_sentences(full_text, language)
    scored = []
    for s in sents:
        text = s.strip()
        if len(text) < 20 or _looks_like_caption_line(text):
            continue
        if language == "zh":
            words = _CJK_TOKEN_RE.findall(text) or [text]
        else:
            words = _EN_TERM_RE.findall(text)
        if not words:
            continue
        hits = sum(1 for w in words if w in term_set)
        ratio = hits / max(len(words), 1)
        if hits >= 3 and ratio >= 0.25:
            scored.append((hits, len(text), text))
    scored.sort(key=lambda x: (-x[0], -x[1]))
    return [t for _, _, t in scored[:top_n]]


def _dim_passive_ratio(sentences: List[str], language: str, pages_text: List[str]) -> Dict:
    if not sentences:
        return {"score": 100.0, "ratio": 0.0, "samples": []}
    if language == "zh":
        passive_sents = [s for s in sentences if _PASSIVE_ZH_RE.search(s)]
    else:
        passive_sents = [s for s in sentences if _PASSIVE_EN_RE.search(s)]
    ratio = len(passive_sents) / len(sentences)
    # 被动占比：<=10% 满分（用户裁定：只扣过高，0% 不扣——操作手册以祈使句为主属正常）
    score = _band_score(ratio, 0.0, 0.10, k_short=0.0, k_long=200.0)
    samples = [{"page": _find_page_of(s, pages_text), "text": s[:120]} for s in passive_sents[:3]]
    return {
        "score": score,
        "ratio": round(ratio * 100, 1),
        "label": f"被动句占比 {round(ratio * 100, 1)}%（建议 ≤ 10%，过低不扣分）",
        "samples": samples,
    }


def _dim_paragraph_length(paragraphs: List[str], language: str) -> Dict:
    if not paragraphs:
        return {"score": 100.0, "avg": 0.0, "samples": []}
    if language == "zh":
        lens = [len(p) for p in paragraphs]
        avg = sum(lens) / len(lens)
        # 中文段长：理想区间 30-150 字（区间制；过短 = 碎片化，过长 = 大段）
        score = _band_score(avg, 30.0, 150.0, k_short=0.5, k_long=0.2)
        label = f"平均段落长度 {avg:.0f} 字（理想 30–150 字）"
    else:
        lens = [len(p.split()) for p in paragraphs]
        avg = sum(lens) / len(lens)
        # 英文段长：理想区间 10-80 词
        score = _band_score(avg, 10.0, 80.0, k_short=2.5, k_long=0.5)
        label = f"平均段落长度 {avg:.0f} 词（理想 10–80 词）"
    long_paras = [p for p in sorted(paragraphs, key=len, reverse=True) if len(p.split()) >= 8 and not _looks_like_caption_line(p)][:3]
    if not long_paras:
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


def analyze_readability(full_text: str, pages_text: Optional[List[str]] = None, language: str = None) -> Dict:
    """可读性量化分析。

    维度与权重：平均句长 25% / 术语密度 20% / 被动句比例 20% / 段落长度 15% / 修饰词堆叠 20%。
    每维度输出 0-100 分、样本例句；总分 = 加权和，映射评级。

    样本量三档（外部评审 P0 采纳项）：句数 < 100 不评分（维度 N/A、综合评分 None、
    评级 insufficient）；100-500 评分但显著标注"样本有限"；> 500 正常评分。
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

    n_sents = len(sentences)
    if n_sents < 100:
        sample_status = "insufficient"
    elif n_sents <= 500:
        sample_status = "limited"
    else:
        sample_status = "sufficient"

    warnings = []
    if sample_status == "insufficient":
        warnings.append(
            f"文本样本量不足（{n_sents} 句），无法可靠评分，本次不输出可读性分数；"
            "网页输入请确认正文非 JS 动态加载，或改用本地 PDF/HTML 上传。"
        )
    elif sample_status == "limited":
        warnings.append(
            f"文本样本量有限（{n_sents} 句），评分仅供参考；建议补充更多正文内容后复核。"
        )

    if sample_status == "insufficient":
        # 不评分：维度分数置 None，综合分/评级空缺，由报告渲染为 N/A
        for k in dims:
            dims[k] = {**dims[k], "score": None}
        suggestions = ["样本不足，未生成改进建议。"]
        return {
            "language": language,
            "overall_score": None,
            "level": "insufficient",
            "level_note": "样本不足，未评分",
            "sample_status": sample_status,
            "warnings": warnings,
            "dimensions": dims,
            "suggestions": suggestions,
            "stats": {
                "sentence_count": n_sents,
                "avg_sentence_len": round(sum(len(s.split()) for s in sentences) / max(n_sents, 1), 1) if sentences else 0,
                "avg_paragraph_len": round(sum(len(p.split()) for p in paragraphs) / max(len(paragraphs), 1), 1) if paragraphs else 0,
                "term_density_pct": dims["term_density"].get("density"),
                "passive_ratio_pct": dims["passive_ratio"].get("ratio"),
            },
        }

    overall = sum(dims[k]["score"] * _WEIGHTS[k] for k in _WEIGHTS)
    overall = _clamp_score(overall)

    # 评级抑制：任一维度显著失分（<55 分）时，综合评级必须下调——
    # 避免出现"术语密度 46 分但综合评级 excellent"的误导性结论。
    level = _level_of(overall)
    level_note = ""
    _quality_rank = {"poor": 1, "fair": 2, "good": 3, "excellent": 4}
    min_dim_score = min(d["score"] for d in dims.values())
    weakest = min(dims, key=lambda k: dims[k]["score"])
    if min_dim_score < 40:
        capped = "poor"
    elif min_dim_score < 55:
        capped = "fair"
    else:
        capped = None
    if capped and _quality_rank[level] > _quality_rank[capped]:
        dim_names = {"sentence_length": "平均句长", "term_density": "术语密度",
                     "passive_ratio": "被动句比例", "paragraph_length": "段落长度",
                     "modifier_stack": "修饰词堆叠"}
        level = capped
        level_note = f"「{dim_names[weakest]}」维度仅 {min_dim_score} 分，综合评级已下调至 {level}"

    suggestions = []
    if dims["sentence_length"]["score"] < 75:
        suggestions.append("句长偏离理想区间（中文 15-40 字 / 英文 8-20 词）：过短检查碎片化，过长建议拆分。")
    if dims["passive_ratio"]["score"] < 75:
        suggestions.append("被动句比例偏高，建议改为主动语态，明确执行主体。")
    if dims["term_density"]["score"] < 75:
        suggestions.append("术语密度偏离理想区间（5%-15%）：过高时首次出现处给出解释或中英文对照。")
    if dims["paragraph_length"]["score"] < 75:
        suggestions.append("段落长度偏离理想区间（中文 30-150 字 / 英文 10-80 词），建议按单一主题拆分或合并。")
    if dims["modifier_stack"]["score"] < 75:
        suggestions.append("存在修饰词堆叠，建议精简定语层级，拆为多句表述。")
    if not suggestions:
        suggestions.append("整体可读性良好，继续保持简洁句式与合理段落结构。")

    return {
        "language": language,
        "overall_score": overall,
        "level": level,
        "level_note": level_note,
        "sample_status": sample_status,
        "warnings": warnings,
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


# ------------------------------------------------------------ 结构统计（客观指标）
# 评审意见采纳项：报告除评分外补充客观事实统计（页数/章节/图表/安全警告），
# 评分可信度存疑时读者仍可获得可验证的结构信息。

# 标题行特征（保守启发式：只统计独立短行；编号标题要求至少两级如 3.2，避开 "1. 操作步骤"）
_HEADING_LINE_RES = [
    re.compile(r"^\s*chapter\s+\d+", re.IGNORECASE),
    re.compile(r"^\s*appendix\s+[a-z0-9]", re.IGNORECASE),
    re.compile(r"^\s*\d+(\.\d+){1,3}[.、\s]\s*\S"),
    re.compile(r"^\s*第[一二三四五六七八九十百\d]+[章节部]"),
]
_HEADING_LINE_MAX = 60
_HEADING_LINE_END_EXCLUDE = ("。", ".", ";", "；", ",", "，", "!", "！", "?", "？")

# 安全警告标签：要求位于行首（手册警告块的常规排式）。两侧都要求标签后为标点/空白/行尾：
# 英文 "WARNING Hot surface" 计、"WARNING signs indicate..." 不计；
# 中文「警告：xxx」计、「注意事项」「注意观察仪器状态」等普通词组不计（交叉审查 P0-1 修复）
_WARNING_LINE_RES = [
    re.compile(r'^(WARNING|CAUTION|DANGER|NOTICE)(?:\s*[!：:）)]|\s+(?=[A-Z0-9"(\u4e00-\u9fff])|$)'),
    re.compile(r"^(警告|注意|危险|警示)(?=[\s!！:：,，。．]|$)"),
    # 名词短语标题形态（Illumina 等厂商手册）："Laser Safety Warning" / "Hot Surface Safety Warning"，
    # 独立标题行、以 Safety Warning 收尾。交叉审查实测驱动的三重守卫防误报：
    #   ① 句首排除词（Figure/Table 图题、"See/Read/The/This" 等正文句首）直接排除；
    #   ② 短语须为大写词序列（Title Case，1-4 个大写词 + Safety Warning），小写句中词无法通过；
    #   ③ 不以句号收尾（正文句子 "Refer to the ... Safety Warning." 不命中）。
    # 中文「激光安全警告」同理，且排除句首动词（请/参见/检查/以上等句子形态）。
    re.compile(
        r"^(?!(?:Figure|Table|See|Read|Refer|The|This|That|These|Please|Check|Note|A|An|Example)\b)"
        r"(?:[A-Z][A-Za-z0-9-]*[\s,]+){0,3}[A-Z][A-Za-z0-9-]*\s+Safety\s+Warning\s*$"
    ),
    re.compile(
        r"^(?!请|参见|参阅|见|查看|检查|参考|阅读|以上|注意|这是|上述|下列|如下|关于)"
        r"[一-龥]{2,10}安全警告(?=[\s：:！!。]|$)"
    ),
]

# 警告相关 unicode 符号（图标型警告的文本层残留，外部评审 P1 采纳项）
# 注意：🛡🚧🚫 为增补平面字符，须写完整码点 \U0001F6E1 等；UTF-16 代理对写法
# （\ud83d\udee1）在 Python3 str 中是孤立代理项，永远匹配不到（交叉审查 P2 修复）
_WARNING_SYMBOL_RE = re.compile(r"[\u26a0\u2620\U0001F6E1\U0001F6A7\U0001F6AB\u26d4]")

# 表格线框检测的页数上限与时间预算：超限跳过/提前结束，避免拖慢同步分析（交叉审查 P1-4）
_TABLE_DETECT_MAX_PAGES = 300
_TABLE_DETECT_TIME_BUDGET = 10.0  # 秒


def _is_heading_line(line: str) -> bool:
    s = line.strip()
    if not s or len(s) > _HEADING_LINE_MAX:
        return False
    if s.endswith(_HEADING_LINE_END_EXCLUDE):
        return False
    return any(rx.match(s) for rx in _HEADING_LINE_RES)


def _is_warning_line(line: str) -> bool:
    s = line.strip()
    if not s or len(s) > _HEADING_LINE_MAX * 2:
        return False
    return any(rx.match(s) for rx in _WARNING_LINE_RES)


def _count_pdf_figures(doc) -> int:
    """统计 PDF 嵌入图片：按 xref 去重（同一 logo 复用只计一次），xref=0 的内联图按出现次数计。"""
    xrefs = set()
    inline = 0
    for page in doc:
        try:
            for img in page.get_images(full=True):
                xref = img[0] if img else 0
                if xref:
                    xrefs.add(xref)
                else:
                    inline += 1
        except Exception:
            continue
    return len(xrefs) + inline


def _count_pdf_tables(doc) -> Tuple[Optional[int], str]:
    """统计 PDF 表格数（PyMuPDF find_tables 线框策略）。返回 (数量, 说明)；不可用时数量为 None。

    - 旧版 PyMuPDF 无 find_tables → None + 说明（不能静默当 0，交叉审查 P1-2）
    - 超时间预算 → 返回已检页的部分计数 + 说明（计数可能偏低）
    """
    if doc.page_count > _TABLE_DETECT_MAX_PAGES:
        return None, f"页数超过 {_TABLE_DETECT_MAX_PAGES}，跳过表格检测以控制耗时"
    if doc.page_count and not hasattr(doc[0], "find_tables"):
        return None, "当前 PyMuPDF 版本不支持 find_tables，表格数不可用"
    import time
    deadline = time.monotonic() + _TABLE_DETECT_TIME_BUDGET
    total = 0
    for page in doc:
        if time.monotonic() > deadline:
            return total, f"表格检测超出 {_TABLE_DETECT_TIME_BUDGET:.0f}s 时间预算，已提前结束（计数可能偏低）"
        try:
            total += len(page.find_tables().tables)
        except Exception:
            continue
    return total, ""


def analyze_structure(filepath: str, full_text: str, pages_text: Optional[List[str]] = None,
                      html_extraction: Optional[Dict] = None) -> Dict:
    """客观结构统计：页数 / 章节数（标题行）/ 图片数 / 表格数 / 安全警告数。

    - 文本类指标（标题行/警告数）：全部格式可用，基于行首特征正则
    - 图片/表格数：PDF 走 fitz（图片按 xref 去重、表格走线框检测），HTML 走标签计数，
      其余格式（DOCX/MD/TXT）暂不支持，以 notes 说明
    """
    notes: List[str] = []
    lines = (full_text or "").splitlines()
    # 标题按文本去重：目录页（TOC）中的 "3.2 Installation …… 12" 不与正文标题重复计数
    heading_texts = {ln.strip() for ln in lines if _is_heading_line(ln)}
    heading_count = len(heading_texts)
    warning_count = sum(1 for ln in lines if _is_warning_line(ln))
    # 警告符号计数（图标型警告的文本层残留）：统一按 full_text 正则口径计数
    # （full_text 即最终正文，PDF/HTML/DOCX 一致；HTML 不再用解析器计数覆盖——
    # 解析器会把 title 等非正文文本计入，与正文口径不一致，交叉审查 P2 修复）
    warning_symbol_count = len(_WARNING_SYMBOL_RE.findall(full_text or ""))
    page_count = len(pages_text) if pages_text else (1 if full_text else 0)
    figure_count: Optional[int] = None
    table_count: Optional[int] = None

    path_low = str(filepath or "").lower()
    if path_low.endswith(".pdf"):
        try:
            import fitz
            doc = fitz.open(filepath)
            try:
                page_count = doc.page_count
                figure_count = _count_pdf_figures(doc)
                table_count, note = _count_pdf_tables(doc)
                if note:
                    notes.append(note)
            finally:
                doc.close()
        except Exception as exc:
            notes.append(f"PDF 结构统计失败：{exc}")
    elif html_extraction is not None:
        # HTML：解析器统计的标签数（已剔除 nav/header/footer 骨架内的元素）
        # v1.1 支持预计算累加统计（多 topic 汇总场景）
        page_count = html_extraction.get("page_count", 1)
        figure_count = html_extraction.get("img_count")
        table_count = html_extraction.get("table_count")
        tag_headings = html_extraction.get("heading_count")
        if isinstance(tag_headings, int):
            # 标签计数（h1-h3）比文本正则更可靠，优先采用
            heading_count = tag_headings
        # 多文本合并时，预计算警告数可能已传入
        precomputed_warning = html_extraction.get("warning_count")
        if isinstance(precomputed_warning, int):
            warning_count = precomputed_warning
        precomputed_symbol = html_extraction.get("warning_symbol_count")
        if isinstance(precomputed_symbol, int):
            warning_symbol_count = precomputed_symbol
    else:
        notes.append("图片/表格统计当前仅支持 PDF 与 HTML 输入")

    # 安全警告 0 标注（外部评审 P1 采纳项）：0 警告 ≠ 真没有，图标/特殊排版可能漏检
    if warning_count == 0:
        notes.append(
            "安全警告数为 0：检测依赖文本关键词匹配（行首 WARNING/CAUTION/警告 等），"
            "图标或特殊排版呈现的安全提示可能未被统计，建议人工复核。"
        )
    if warning_symbol_count > 0:
        notes.append(f"文本层检测到 {warning_symbol_count} 处警告类符号（⚠/☠ 等），可能对应图标型安全提示。")

    return {
        "page_count": page_count,
        "heading_count": heading_count,
        "figure_count": figure_count,
        "table_count": table_count,
        "warning_count": warning_count,
        "warning_symbol_count": warning_symbol_count,
        "notes": notes,
    }


def analyze_document(filepath: str, full_text: str, pages_text: Optional[List[str]] = None,
                     html_extraction: Optional[Dict] = None) -> Dict:
    """文档总入口：返回 {tool_analysis, readability, structure_stats} 供存储与报告渲染。"""
    return {
        "tool_analysis": analyze_tool_usage(filepath, full_text, pages_text),
        "readability": analyze_readability(full_text, pages_text),
        "structure_stats": analyze_structure(filepath, full_text, pages_text, html_extraction),
    }
