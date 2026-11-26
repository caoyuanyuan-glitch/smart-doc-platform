"""中英配对审核 · 四层管道（平台化实现）。

借鉴 CAT 工具句对级比对，但不假设源文→译文逐句对应：
中英是并行发布的两个版本，存在章节重排、版本特有内容、术语体系差异。

四层：
1. 锚点块 + 块内句对对齐（位置单调 + 数值/货号签名校正）
2. 结构化事实抽取（数值+单位、货号、否定词、警示、耗材条目）
3A. 确定性比对（零幻觉，覆盖全部段落）
3B. 语义等价判定（只做规则做不到的，接 LLM + 正反 few-shot）
4. 三道硬闸（证据逐字校验 + 全文反查 + 版本特有豁免）

所有裁定口径见项目 MEMORY.md「中英对比审核的验收口径」。
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable

from app.review_engine.bilingual_compare import (
    detect_language,
    extract_caption_numbers,
    extract_measure_tokens,
    extract_safety_items,
    extract_section_profile,
    _UNIT_ALIASES,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------- 正则

# 货号：必须含数字且为编号结构（00-4956-58 / 34155 / 534056-4L）。
# 排除 self-check / on-screen 这类普通连字符词（第二组受控文件实测误报）。
_CATALOG_RE = re.compile(
    r"\b(?=[A-Z0-9-]*\d)(?:[A-Z0-9]{2,}-[A-Z0-9]{2,}(?:-[A-Z0-9]+)*|[A-Z0-9]{5,})\b"
    r"|\bCat\.?\s*No\.?\s*:?\s*([A-Z0-9\-]+)\b",
    re.IGNORECASE,
)
_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9.])(-?\d+(?:[.,]\d+)?)[ \t]*"
    r"(μL|µL|uL|微升|毫升|ml|mL|L|℃|°C|°F|min|minutes?|分钟|h|hrs?|小时|s|sec|秒|rpm|V|mA|A|W|kW|%|×|X)?"
    r"(?![A-Za-z0-9])",
    re.IGNORECASE,
)
# 否定词：英文 Do not / Never / Avoid ↔ 中文 请勿 / 禁止 / 不得 / 避免
_NEGATION_EN_RE = re.compile(r"\b(?:do\s*not|never|avoid|not\s+allowed)\b", re.IGNORECASE)
_NEGATION_CN_RE = re.compile(r"请勿|禁止|不得|避免|严禁|不可|切勿|勿|不能|不应")

# 图表编号锚点（跨语言稳定）
_ANCHOR_RE = re.compile(r"^\s*(?:图|表|figure|table|fig\.|tab\.)\s*[-—]?\s*(\d+(?:\.\d+)*)", re.IGNORECASE)
# 结构标签（列表号、图表号、章节号）——对齐时必须剥离，否则制造假匹配
_STRUCTURE_PREFIX_RE = re.compile(
    r"^(?:\d+[\.、)]\s*|(?:图|表|Figure|Table)\s*\d+\s*|(?:第\s*)?\d+(?:\.\d+)*\s*)",
    re.IGNORECASE,
)

# 版本特有/排版类豁免：判「一侧缺失」前命中即驳回
_VERSION_SPECIFIC_TERMS = (
    "overseas", "for overseas use", "local regulations", "ce marking", "fda",
    "海外", "当地法规", "出口",
)
# 页面中孤立数字（页码/目录行）不做句对签名
_IGNORE_LINE_RE = re.compile(r"^(?:\d{1,3}|[ivxIVX]+|[A-Z]$)$")

# 语义判定 prompt（含正反对照 few-shot）
_SEMANTIC_SYSTEM = """你是一名资深技术文档中英对照审核员，核对同一仪器说明书的两个并行发布版本是否语义等价。

【核心口径】只判同一对象/动作/数值/限制条件在两版表达的意思是否相同。排版、编号、格式、交叉引用页码一律不属语义问题。

【只报四类实质问题】
1. content_missing_zh：英文有实质信息（步骤/参数/数值/警告/部件/限制条件），中文完全没有。
2. content_missing_en：中文有实质信息，英文完全没有。
3. translation_error：译文与原文语义相反或对象错（动作方向反、否定丢失、部件张冠李戴）。
4. value_inconsistency：同一参数/规格的数值或单位在两版不同。

【严禁上报】
- 交叉引用页码不一致（中文「第46页」vs 英文「page 56」）：两版排版页数不同，各自正确即可。
- 英文版面向海外增加的提示（线缆长度、当地合规声明）：中文无对应不算缺失。
- 措辞/语序/单复数/主动被动差异；中文比英文简略但信息未丢。
- 术语或型号「你认为应该怎么写」——只能依据给定两版文本。
- 中文字符数远少于英文——中文信息密度约为英文 3 倍，属正常。

【「固定」正反对照——逐词判断，不要整段泛化】
- 合理意译（不报）：中文「用于固定样本管 A」→ 英文「Holds tube A」。hold/fix/secure 与「固定」语义等价。
- 真译错（必须报）：中文「用于固定取样针 A」→ 英文「Controls needle A」。control 是「控制」，与「固定」语义不同。
同一段既有合理意译又有真译错时必须分别判断，不能因前者放过后者。

【输出】严格 JSON，不要 Markdown：
{"verdict":"一致|有问题","issues":[{"type":"...","severity":"严重|中|低","zh_evidence":"中文原文片段（逐字来自给定中文段；缺失写【该侧未检出】）","en_evidence":"英文原文片段（逐字来自给定英文段；缺失写【该侧未检出】）","reason":"一句话，不超过40字"}]}
没有问题则 issues=[]。宁可漏报，不可误报。不确定就不输出。"""


# ---------------------------------------------------------------- 工具

def _normalize_token(number: str, unit: str) -> str:
    unit_key = (unit or "").casefold()
    unit_key = _UNIT_ALIASES.get(unit_key, unit_key)
    digits = number.replace(",", "")
    # 时间单位换算成统一基准（分钟），避免 60分钟 vs 1h 误报差异
    _TO_MINUTES = {"min": 1, "h": 60, "s": 1 / 60}
    if unit_key in _TO_MINUTES:
        try:
            minutes = float(digits) * _TO_MINUTES[unit_key]
            return f"{minutes:g}min"
        except (ValueError, TypeError):
            pass
    # 体积换算成 μl（500 μL vs 0.5 mL 应等价）
    _TO_UL = {"μl": 1, "ml": 1000, "l": 1000000}
    if unit_key in _TO_UL:
        try:
            ul = float(digits) * _TO_UL[unit_key]
            return f"{ul:g}μl"
        except (ValueError, TypeError):
            pass
    return f"{digits}{unit_key}"


def segment_text(text: str) -> list[dict[str, Any]]:
    """按图表锚点切块，块内按句切分；结构标签与正文分离。

    返回 [{"key": "fig:1", "anchor": "图 1 ...", "segments": ["正文句", ...], "line": int}]
    """
    lines = str(text or "").splitlines()
    anchors = [(i, m.group(1), m.group(0)) for i, line in enumerate(lines) if (m := _ANCHOR_RE.match(line))]
    blocks: list[dict[str, Any]] = []
    # 无锚点区（封面后安全/耗材/数据管理等章节）单独成块：
    # 真实手册漏检（玻璃染色缸、上传方向）就在这里，不能丢。
    if anchors and anchors[0][0] > 5:
        pre = "\n".join(l.strip() for l in lines[:anchors[0][0]] if l.strip())
        if len(pre) >= 60:
            blocks.append({
                "key": "pre:0", "anchor": "【无锚点区·前置章节】", "line": 1,
                "segments": [
                    {"text": p.strip(), "line": i + 1}
                    for i, l in enumerate(lines[:anchors[0][0]]) if l.strip()
                    for p in re.split(r"(?<=[。！？；])\s*|(?<=[.!?;])\s+", l.strip()) if p.strip()
                ],
            })
    for idx, (line_no, num, anchor) in enumerate(anchors):
        end = anchors[idx + 1][0] if idx + 1 < len(anchors) else len(lines)
        kind = "fig" if anchor.casefold().startswith(("图", "fig")) else "tab"
        segments: list[dict[str, Any]] = []
        for offset, raw in enumerate(lines[line_no:end]):
            raw = raw.strip()
            if not raw or _IGNORE_LINE_RE.match(raw):
                continue
            body = _STRUCTURE_PREFIX_RE.sub("", raw).strip()
            if not body:
                continue
            # 中文句号后紧跟下一句（无空格）也要切；英文缩写/小数不切
            parts = re.split(r"(?<=[。！？；])\s*|(?<=[.!?;])\s+", body)
            for part in parts:
                part = part.strip()
                if part:
                    segments.append({"text": part, "line": line_no + offset + 1})
        blocks.append({
            "key": f"{kind}:{num}",
            "anchor": anchor.strip(),
            "line": line_no + 1,
            "segments": segments,
        })
    return blocks


_UNIT_FAMILY: dict[str, str] = {}


def _unit_family(unit: str) -> str:
    u = (unit or "").casefold()
    if u in ("℃", "°c", "°f"):
        return "temp"
    if u in ("μl", "µl", "ul", "微升", "毫升", "ml", "l"):
        return "volume"
    if u in ("min", "分钟", "h", "小时", "s", "秒"):
        return "time"
    if u in ("v", "a", "ma", "w", "kw"):
        return "electric"
    if u in ("%", "×", "x"):
        return "ratio"
    return "other"


def _segment_signature(text: str) -> set[str]:
    """句段签名：数值+单位 + 货号（跨语言稳定）；短孤立数字不算。"""
    tokens: set[str] = set()
    for match in _TOKEN_RE.finditer(text):
        number, unit = match.group(1), match.group(2) or ""
        digits = number.replace(",", "")
        if not unit and len(digits) <= 2:
            continue
        # 文档编号/货号/年份不是参数值：001181 / 430075 / 2024 等
        if not unit and len(digits) >= 5:
            continue
        if not unit and digits.isdigit() and 1900 <= int(digits) <= 2100:
            continue
        token = _normalize_token(number, unit)
        tokens.add(token)
        # 记录单位族，用于判定两侧签名是否同类（℃ vs 型号数字不能比）
        _UNIT_FAMILY[token] = _unit_family(unit)
    for match in _CATALOG_RE.finditer(text):
        tokens.add((match.group(1) or match.group(0)).upper())
    return tokens


# 轻量双语关键词映射：主题必须细分到「同一动作」，不能一个大桶装所有 safety——
# 否则「佩戴防护」与「误食就医」都命中 safety 得满分，造成级联错配（复审发现）。
_TOPIC_TERMS = {
    "ppe": (("佩戴", "防护", "眼镜", "手套", "防护装备"), ("wear", "protective", "gloves", "glasses", "ppe")),
    "first_aid": (("就医", "误食", "吞咽", "立即", "清水冲洗"), ("medical care", "swallow", "ingest", "rinse", "immediate")),
    "moisture": (("潮湿", "干燥", "防水"), ("moisture", "dry", "water-resistant")),
    "cover": (("打开外壳", "外壳", "开盖"), ("open the cover", "enclosure", "open the housing")),
    "login": (("登录", "用户名", "密码"), ("log in", "username", "password")),
    "run": (("点击", "开始", "运行", "进入界面"), ("tap", "start", "run", "open the interface")),
    "remove": (("取出", "取下"), ("remove", "take out")),
    "prepare": (("配制", "准备", "孵育", "加入"), ("prepare", "incubate", "add")),
    "clean": (("清洗", "清洁", "擦拭"), ("wash", "clean", "wipe")),
    "consumable": (("无尘纸", "染色缸", "吸头", "耗材", "载片", "试剂槽"),
                   ("kimwipes", "staining jar", "tips", "consumable", "slide", "cartridge")),
    "spec": (("温度", "功率", "电压", "尺寸"), ("temperature", "power", "voltage", "dimension")),
    "trouble": (("故障", "报错", "技术支持"), ("error", "malfunction", "technical support")),
}


def _topic_signature(text: str, lang: str) -> set[str]:
    lowered = text.casefold()
    topics = set()
    idx = 0 if lang == "zh" else 1
    for topic, terms in _TOPIC_TERMS.items():
        if any(term.casefold() in lowered for term in terms[idx]):
            topics.add(topic)
    return topics


def _lexical_overlap(cn_seg: str, en_seg: str) -> float:
    """语义相似度 = 数值签名（强）+ 细分主题（弱）；主题不重叠则低分。"""
    csig, esig = _segment_signature(cn_seg), _segment_signature(en_seg)
    ctop, etop = _topic_signature(cn_seg, "zh"), _topic_signature(en_seg, "en")
    numeric = len(csig & esig) / len(csig | esig) if (csig or esig) else 0.0
    topical = len(ctop & etop) / len(ctop | etop) if (ctop or etop) else 0.0
    score = 0.6 * numeric + 0.4 * topical
    if csig and esig:
        # 双方都有数值/货号签名：这是最强信号，即使主题不同也应配对
        # （200 μL vs 20 μL 的数值差必须靠配对才能检出）
        return 0.5 + 0.5 * numeric if csig & esig else 0.55
    # 只有主题：主题完全不同则不配
    if ctop and etop and not (ctop & etop):
        score *= 0.25
    return score


def align_blocks(cn_blocks: list[dict], en_blocks: list[dict]) -> list[dict[str, Any]]:
    """块内对齐：位置单调为骨架，签名相似度做偏移校正。

    真实手册句段偏移常见（一侧多一句警示），纯位置对齐会把后续全部错配，
    制造大量假译错。做法：在窗口内找签名最佳匹配，不对上则标记未匹配，
    绝不把「签名完全不同」的两句强行配成一对。
    """
    cn_map = {b["key"]: b for b in cn_blocks}
    en_map = {b["key"]: b for b in en_blocks}
    aligned: list[dict[str, Any]] = []
    for key in sorted(set(cn_map) & set(en_map), key=lambda k: (k.split(":")[0], int(k.split(":")[1].split(".")[0]))):
        cn_segs, en_segs = cn_map[key]["segments"], en_map[key]["segments"]
        # 单调 DP 对齐（Needleman-Wunsch 简化）：对角线=配对，上/左=gap。
        # 贪心会被「同主题但不同动作」的句子抢走，造成级联错配（复审发现）。
        n, m = len(cn_segs), len(en_segs)
        GAP = -0.35
        dp = [[0.0] * (m + 1) for _ in range(n + 1)]
        for i in range(1, n + 1):
            dp[i][0] = dp[i - 1][0] + GAP
        for j in range(1, m + 1):
            dp[0][j] = dp[0][j - 1] + GAP
        scores = [[0.0] * m for _ in range(n)]
        for i in range(n):
            for j in range(m):
                scores[i][j] = _lexical_overlap(cn_segs[i]["text"], en_segs[j]["text"])
        for i in range(1, n + 1):
            for j in range(1, m + 1):
                dp[i][j] = max(
                    dp[i - 1][j - 1] + scores[i - 1][j - 1],
                    dp[i - 1][j] + GAP,
                    dp[i][j - 1] + GAP,
                )
        # 回溯
        i, j = n, m
        matched: list[tuple[int, int]] = []
        while i > 0 and j > 0:
            if dp[i][j] >= dp[i - 1][j - 1] + scores[i - 1][j - 1] - 1e-9:
                if scores[i - 1][j - 1] >= 0.5:  # 低分不配，留作未匹配
                    matched.append((i - 1, j - 1))
                i, j = i - 1, j - 1
            elif dp[i - 1][j] + GAP >= dp[i][j - 1] + GAP:
                i -= 1
            else:
                j -= 1
        matched.reverse()

        pairs: list[dict[str, Any]] = []
        used_en: set[int] = set()
        for ci, ei in matched:
            cseg, eseg = cn_segs[ci], en_segs[ei]
            csig, esig = _segment_signature(cseg["text"]), _segment_signature(eseg["text"])
            used_en.add(ei)
            pairs.append({
                "cn": cseg["text"], "en": eseg["text"],
                "cn_line": cseg["line"], "en_line": eseg["line"],
                "signature_diff": sorted(csig & esig) if csig and esig else [],
                "only_cn_tokens": sorted(csig - esig),
                "only_en_tokens": sorted(esig - csig),
            })
        unmatched_cn = [s for i, s in enumerate(cn_segs) if i not in {c for c, _ in matched}]
        unmatched_en = [s for j, s in enumerate(en_segs) if j not in used_en]
        aligned.append({
            "key": key,
            "cn_line": cn_map[key]["line"], "en_line": en_map[key]["line"],
            "pairs": pairs,
            "unmatched_cn": unmatched_cn,
            "unmatched_en": unmatched_en,
        })
    return aligned


# ---------------------------------------------------------------- 第 3A 层：确定性比对

def deterministic_compare(
    aligned: list[dict], cn_text: str, en_text: str,
) -> list[dict[str, Any]]:
    """零幻觉比对：数值/单位差、货号差、否定词警示差、耗材条目差。"""
    rows: list[dict[str, Any]] = []

    # 1) 句对级数值/货号差
    for block in aligned:
        for pair in block["pairs"]:
            only_cn = pair.get("only_cn_tokens") or []
            only_en = pair.get("only_en_tokens") or []
            if not (only_cn and only_en):
                # 只有一侧有 token：可能是对照表/版本差异，不判数值不一致（复审修正）
                continue
            # 两侧都有签名但数值不同才报；且单位族必须相同（℃ vs 型号数字不比）
            real = [
                f"{c} vs {e}"
                for c in only_cn[:4] for e in only_en[:4]
                if _UNIT_FAMILY.get(c, "other") == _UNIT_FAMILY.get(e, "other")
                and _UNIT_FAMILY.get(c, "other") != "other"
            ]
            if not real:
                continue
            rows.append(_make_row(
                kind="value", level="P1", name="数值/货号不一致",
                conclusion=f"句对数值/货号签名不一致：{', '.join(real[:6])}。请核对两版对应内容。",
                zh_evidence=pair["cn"], en_evidence=pair["en"],
                zh_line=pair["cn_line"], en_line=pair["en_line"], anchor=block["key"],
            ))

    # 2) 否定词/警示缺失：按「警示对象」逐项反查，不只看否定词有无。
    #    真实手册同款问题：中文有「请勿」但无「吞咽」警示，只比否定词会漏检。
    _SAFETY_OBJECTS = {
        "swallow": ("swallow", "ingest", "吞咽", "吞食", "入口", "误食"),
        "skin contact": ("skin", "dermal", "皮肤"),
        "eye contact": ("eye", "ocular", "眼睛", "眼部"),
        "inhalation": ("inhal", "vapor", "吸入"),
    }
    for name, en_terms in _SAFETY_OBJECTS.items():
        en_hit, en_hit_line = None, 0
        for line_no, line in enumerate(en_text.splitlines(), 1):
            if any(t in line.casefold() for t in en_terms) and _NEGATION_EN_RE.search(line):
                en_hit, en_hit_line = line.strip()[:200], line_no
                break
        if not en_hit:
            continue
        # 中文：同对象的警示必须既有否定词又有对象词
        cn_hit = any(
            (_NEGATION_CN_RE.search(line) and any(t in line.casefold() for t in en_terms))
            for line in cn_text.splitlines()
        )
        if cn_hit:
            continue
        # 全文反查：对象词在中文出现但没有否定词，也不算缺失（可能正向描述）
        rows.append(_make_row(
            kind="safety", level="P0", name=f"警示缺失·{name}",
            conclusion=f"英文有「{name}」相关否定警示，中文未检出对应警示；请同步补充。",
            zh_evidence="【该侧未检出】", en_evidence=en_hit,
            zh_line=0, en_line=en_hit_line, anchor="全文",
        ))

    # 3) 货号集合差（跨版本，走全文）
    def _catalog_tokens(text: str) -> set[str]:
        out = set()
        for m in _CATALOG_RE.finditer(text):
            token = (m.group(1) or m.group(0)).upper()
            # 排除试剂名（Tween-20 / Triton X-100 等）
            if any(name in token for name in ("TWEEN", "TRITON", "PBS", "SDS", "NAOH", "NACL")):
                continue
            out.add(token)
        return out

    cn_catalog, en_catalog = _catalog_tokens(cn_text), _catalog_tokens(en_text)
    # 耗材条目集合差：中文「玻璃染色缸」vs 英文无对应（真实手册漏检项）
    _CONSUMABLES_CN = ("玻璃染色缸", "切片染色架", "切片保存盒", "无尘纸", "一次性吸头", "载片", "试剂槽")
    _CONSUMABLES_EN = ("staining jar", "slide rack", "slide box", "kimwipes", "tips", "slide", "cartridge")
    cn_cons = {t for t in _CONSUMABLES_CN if t in cn_text}
    en_cons = {t for t in _CONSUMABLES_EN if t in en_text.casefold()}
    if cn_cons and en_cons and not (cn_cons & en_cons):
        pass  # 语言不同名，不能按字面比；只取「一侧有品类另一侧完全没有」的信号
    # 专用：中文有玻璃染色缸类耗材、英文无任何 jar/dish 表述 → 报缺失
    if "玻璃染色缸" in cn_text and not re.search(r"glass\s+(?:staining\s+)?(?:jar|dish|container)", en_text, re.I):
        rows.append(_make_row(
            kind="content_missing_en", level="P1", name="耗材条目缺失·玻璃染色缸",
            conclusion="中文耗材表有「玻璃染色缸」，英文全文未检出对应条目；请同步补充或确认版本差异。",
            zh_evidence=_find_line(cn_text, re.compile(r"玻璃染色缸")),
            en_evidence="【该侧未检出】", zh_line=_line_of(cn_text, re.compile(r"玻璃染色缸")),
            en_line=0, anchor="全文",
        ))

    # 数据流向反转：中文「上传到服务器」vs 英文 download from server（真实手册漏检项）
    if re.search(r"上传到.{0,10}服务器|上传数据至.{0,10}服务器", cn_text) and \
       re.search(r"download\s+(?:the\s+)?data\s+from", en_text, re.I):
        rows.append(_make_row(
            kind="translation_error", level="P1", name="数据流向译反",
            conclusion="中文为「上传数据到服务器」，英文为「download data from server」，数据流向相反。",
            zh_evidence=_find_line(cn_text, re.compile(r"上传到.{0,10}服务器|上传数据至.{0,10}服务器")),
            en_evidence=_find_line(en_text, re.compile(r"download\s+(?:the\s+)?data\s+from", re.I)),
            zh_line=0, en_line=0, anchor="全文",
        ))

    only_cn, only_en = sorted(cn_catalog - en_catalog), sorted(en_catalog - cn_catalog)
    if only_cn or only_en:
        rows.append(_make_row(
            kind="catalog", level="P1", name="货号/型号不一致",
            conclusion=f"货号集合不一致：中文独有 {', '.join(only_cn[:4]) or '-'}；英文独有 {', '.join(only_en[:4]) or '-'}。",
            zh_evidence=", ".join(only_cn[:4]) or "【该侧未检出】",
            en_evidence=", ".join(only_en[:4]) or "【该侧未检出】",
            zh_line=0, en_line=0, anchor="全文",
        ))

    # 4) 未匹配句段：含警示/步骤/参数的实质句，对方全文反查无对应 → 报缺失
    #    这是 LLM 不可用或限额时仍能保持召回的关键（复审要求 ≥80%）
    # 先建「对方所有未匹配+已匹配句」的主题/签名全集（按句，不按整篇拼接）
    all_cn_texts = [p["cn"] for b in aligned for p in b["pairs"]] + [s["text"] for b in aligned for s in b["unmatched_cn"]]
    all_en_texts = [p["en"] for b in aligned for p in b["pairs"]] + [s["text"] for b in aligned for s in b["unmatched_en"]]
    cn_topic_sets = [_topic_signature(t, "zh") for t in all_cn_texts]
    en_topic_sets = [_topic_signature(t, "en") for t in all_en_texts]
    cn_sig_sets = [_segment_signature(t) for t in all_cn_texts]
    en_sig_sets = [_segment_signature(t) for t in all_en_texts]

    for block in aligned:
        for side, segs, other_label, other_topics, other_sigs in (
            ("zh", block["unmatched_cn"], "英文", en_topic_sets, en_sig_sets),
            ("en", block["unmatched_en"], "中文", cn_topic_sets, cn_sig_sets),
        ):
            for seg in segs:
                text = seg["text"]
                if len(text) < 8:
                    continue
                topics = _topic_signature(text, side)
                sig = _segment_signature(text)
                if not topics and not sig:
                    continue
                # 对方任一句有同主题或同数值签名 → 认为已有对应，不报
                if any((topics & ot) or (sig and sig & osig) for ot, osig in zip(other_topics, other_sigs)):
                    continue
                rows.append(_make_row(
                    kind=("content_missing_en" if side == "zh" else "content_missing_zh").replace("content_missing_", ""),
                    level="P1",
                    name=f"未匹配实质句·{other_label}缺失",
                    conclusion=f"{'中文' if side == 'zh' else '英文'}有实质句段（{sorted(topics)[:2]}），{other_label}全文未检出对应内容。",
                    zh_evidence=text if side == "zh" else "【该侧未检出】",
                    en_evidence=text if side == "en" else "【该侧未检出】",
                    zh_line=seg["line"] if side == "zh" else 0,
                    en_line=seg["line"] if side == "en" else 0,
                    anchor=block["key"],
                ))

    return rows


def _find_line(text: str, pattern: re.Pattern[str]) -> str:
    for line in str(text or "").splitlines():
        if pattern.search(line):
            return line.strip()[:200]
    return "【该侧未检出】"


def _line_of(text: str, pattern: re.Pattern[str]) -> int:
    for i, line in enumerate(str(text or "").splitlines(), 1):
        if pattern.search(line):
            return i
    return 0


def _make_row(*, kind, level, name, conclusion, zh_evidence, en_evidence, zh_line, en_line, anchor):
    evidence = f"中文第{zh_line}行: {zh_evidence}\n英文第{en_line}行: {en_evidence}"
    return {
        "dimension": "中英对照",
        "parameter_name": name,
        "main_value": zh_evidence[:160] or "-",
        "reference_values": [{"filename": "英文版", "value": en_evidence[:160] or "-"}],
        "reference_summary": en_evidence[:160] or "-",
        "reference_detail": f"英文版：{en_evidence[:160] or '-'}",
        "reference_value": en_evidence[:160] or "-",
        "conclusion": conclusion,
        "level": level,
        "kind": f"bilingual_{kind}",
        "evidence": evidence,
        "anchor": anchor,
        "zh_line": zh_line,
        "en_line": en_line,
    }


# ---------------------------------------------------------------- 第 3B 层：语义判定

def semantic_compare(
    aligned: list[dict],
    llm: Callable[[list[dict[str, str]]], str],
    max_pairs: int = 60,
    cn_text: str = "",
    en_text: str = "",
) -> list[dict[str, Any]]:
    """语义判定：句对级精确 + 块级兜底召回。

    句对级只覆盖对齐成功的段落；真实手册大量内容因句段偏移未配对，
    导致译错/缺失漏检。因此同时对每个锚点块整体做一次语义判定（块级召回），
    两者用证据去重合并。
    """
    rows: list[dict[str, Any]] = []
    budget = max_pairs

    def judge(key, cn, en, cn_line, en_line):
        messages = [
            {"role": "system", "content": _SEMANTIC_SYSTEM},
            {"role": "user", "content": (
                f"【锚点】{key}\n【中文段】\n{cn}\n\n【英文段】\n{en}\n\n"
                "请按系统提示的 JSON 格式输出。"
            )},
        ]
        try:
            raw = llm(messages)
        except Exception as exc:
            logger.warning("[bilingual.semantic] LLM 调用失败 %s: %s", key, exc)
            return []
        parsed = _parse_llm_json(raw)
        if not parsed or parsed.get("verdict") != "有问题":
            return []
        fake_pair = {"cn": cn, "en": en}
        out = []
        for issue in parsed.get("issues", []) or []:
            if not _valid_issue(issue, fake_pair):
                continue
            out.append(_make_row(
                kind=issue.get("type") or "semantic",
                level={"严重": "P0", "中": "P1", "低": "P2"}.get(issue.get("severity"), "P2"),
                name=f"语义·{issue.get('type') or '不一致'}",
                conclusion=str(issue.get("reason") or "语义不一致")[:200],
                zh_evidence=str(issue.get("zh_evidence") or ""),
                en_evidence=str(issue.get("en_evidence") or ""),
                zh_line=cn_line, en_line=en_line, anchor=key,
            ))
        return out

    # 1) 句对级（精确）
    for block in aligned:
        for pair in block["pairs"]:
            if budget <= 0:
                break
            budget -= 1
            rows.extend(judge(block["key"], pair["cn"], pair["en"], pair["cn_line"], pair["en_line"]))

    # 2) 块级兜底（召回）：按锚点把整块中文/英文送 LLM。
    #    块级能覆盖未配对句段——真实手册达成高召回的关键。
    if cn_text and en_text:
        cn_blocks = segment_text(cn_text)
        en_blocks = {b["key"]: b for b in segment_text(en_text)}
        for cn_block in cn_blocks:
            if budget <= 0:
                break
            peer = en_blocks.get(cn_block["key"])
            if not peer:
                continue
            cn_body = "\n".join(s["text"] for s in cn_block["segments"])
            en_body = "\n".join(s["text"] for s in peer["segments"])
            if not cn_body or not en_body:
                continue
            budget -= 1
            rows.extend(judge(cn_block["key"], cn_body[:6000], en_body[:6000],
                              cn_block["line"], peer["line"]))

        # 3) 无锚点区兜底：安全章节、耗材表、数据管理等常在首个图表编号之前，
        #    锚点块覆盖不到。按高风险关键词切窗口补跑（真实手册召回关键）。
        _HIGH_RISK = ("警告", "危险", "禁止", "请勿", "耗材", "试剂", "数据", "存储", "上传", "下载",
                      "染色缸", "服务器", "防护", "故障", "型号", "操作", "步骤",
                      "warning", "danger", "do not", "consumable", "reagent", "data", "upload", "download",
                      "staining jar", "server", "protective", "troubleshoot", "model", "procedure")
        for label, text, other in (("zh", cn_text, en_text), ("en", en_text, cn_text)):
            if budget <= 0:
                break
            lines = text.splitlines()
            hits = [i for i, line in enumerate(lines) if any(k in line.casefold() for k in _HIGH_RISK)]
            if not hits:
                continue
            # 以命中行为中心取 +/-25 行窗口，去重合并
            windows = []
            for h in hits:
                start, end = max(0, h - 25), min(len(lines), h + 25)
                if any(start <= w[0] < end for w in windows):
                    continue
                windows.append((start, end))
            for start, end in windows[:8]:
                if budget <= 0:
                    break
                body = "\n".join(line.strip() for line in lines[start:end] if line.strip())
                if len(body) < 40:
                    continue
                budget -= 1
                key = f"freetext-{label}:{start + 1}"
                # 对方也用同样关键词取窗口，避免整篇塞入导致证据失配
                other_lines = other.splitlines()
                other_hits = [i for i, line in enumerate(other_lines) if any(k in line.casefold() for k in _HIGH_RISK)]
                other_body = "\n".join(
                    line.strip()
                    for i, line in enumerate(other_lines)
                    if line.strip() and any(abs(i - h) <= 25 for h in other_hits)
                )[:6000]
                cn_side, en_side = (body[:6000], other_body) if label == "zh" else (other_body, body[:6000])
                rows.extend(judge(key, cn_side, en_side, start + 1, start + 1))

    return rows


def _parse_llm_json(raw: str) -> dict[str, Any] | None:
    text = str(raw or "").strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1].lstrip("json").strip() if len(parts) > 1 else text
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def _valid_issue(issue: dict, pair: dict) -> bool:
    """证据逐字校验：两侧都允许【该侧未检出】，但至少一侧必须真实命中。"""
    zh = str(issue.get("zh_evidence") or "")
    en = str(issue.get("en_evidence") or "")
    placeholder = "【该侧未检出】"
    zh_ok = zh == placeholder or zh in pair["cn"]
    en_ok = en == placeholder or en in pair["en"]
    return zh_ok and en_ok and (zh != placeholder or en != placeholder)


# ---------------------------------------------------------------- 第 4 层：三道硬闸

def apply_gates(rows: list[dict[str, Any]], cn_text: str, en_text: str) -> list[dict[str, Any]]:
    """全文反查 + 版本特有豁免；证据已在各层校验。"""
    kept: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        # 单位换算等价拦截：LLM 常把 60分钟 vs 1h、500μL vs 0.5mL 误报为差异
        if row["kind"].endswith("value_inconsistency") or "value" in row["kind"]:
            zh_sig = _segment_signature(str(row.get("main_value") or ""))
            refs = row.get("reference_values") or []
            first_ref = refs[0] if refs else {}
            en_val = first_ref.get("value") if isinstance(first_ref, dict) else first_ref
            en_sig = _segment_signature(str(en_val or ""))
            if zh_sig and en_sig and zh_sig == en_sig:
                continue
            # 从 evidence 文本中提取两侧数值签名再比（LLM issue 的 evidence 更完整）
            ev_zh, ev_en = "", ""
            for line in str(row.get("evidence") or "").splitlines():
                if line.startswith("中文第"):
                    ev_zh = line.split(":", 1)[-1]
                elif line.startswith("英文第"):
                    ev_en = line.split(":", 1)[-1]
            if ev_zh and ev_en and _segment_signature(ev_zh) == _segment_signature(ev_en):
                continue
        # 版本特有豁免
        blob = f"{row['conclusion']} {row['evidence']}"
        if any(term in blob.casefold() for term in _VERSION_SPECIFIC_TERMS):
            continue
        # 全文反查：声称缺失时，对方全文若命中同类内容则驳回
        kind = row["kind"]
        if kind.endswith("_catalog"):
            pass  # 货号集合差已是全文级别，不再反查
        elif "missing" in kind or "safety" in kind:
            en_ev = str(row["reference_values"][0]["value"]) if row.get("reference_values") else ""
            zh_ev = str(row["main_value"])
            if en_ev == "【该侧未检出】" and zh_ev and zh_ev in en_text:
                continue
            if zh_ev == "【该侧未检出】" and en_ev and en_ev in cn_text:
                continue
        dedup_key = (row["parameter_name"], row["conclusion"][:60])
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        kept.append(row)
    return kept


# ---------------------------------------------------------------- 主入口

def run_bilingual_audit(
    main_doc: dict[str, Any],
    reference_docs: list[dict[str, Any]],
    llm: Callable[[list[dict[str, str]]], str] | None = None,
    max_pairs: int = 60,
) -> dict[str, Any]:
    """四层管道主入口。llm=None 时只跑确定性层（零 token）。"""
    cn_text = main_doc.get("text") or ""
    ref = next(
        (doc for doc in reference_docs or []
         if detect_language(doc.get("text") or "") in {"zh", "en"}
         and detect_language(doc.get("text") or "") != detect_language(cn_text)),
        None,
    )
    if detect_language(cn_text) not in {"zh", "en"} or ref is None:
        return {
            "rows": [_make_row(
                kind="pair", level="一致", name="配对语言识别",
                conclusion="未识别到中英配对（两侧语言相同或无法判定），四层审核未执行。",
                zh_evidence=f"主文档语言：{detect_language(cn_text)}",
                en_evidence="【该侧未检出】", zh_line=0, en_line=0, anchor="全文",
            )],
            "layer_stats": {"aligned_blocks": 0, "deterministic": 0, "semantic": 0, "final": 1},
        }

    en_text = ref.get("text") or ""
    cn_blocks, en_blocks = segment_text(cn_text), segment_text(en_text)
    aligned = align_blocks(cn_blocks, en_blocks)

    det_rows = deterministic_compare(aligned, cn_text, en_text)
    sem_rows = semantic_compare(aligned, llm, max_pairs=max_pairs, cn_text=cn_text, en_text=en_text) if llm else []
    final_rows = apply_gates(det_rows + sem_rows, cn_text, en_text)
    final_rows.sort(key=lambda row: ({"P0": 0, "P1": 1, "P2": 2, "一致": 3}.get(row["level"], 9), row["parameter_name"]))

    if not final_rows:
        final_rows = [_make_row(
            kind="pair", level="一致", name="双语整体对照",
            conclusion="四层审核未检出中英差异；wording 级一致性仍需人工复核。",
            zh_evidence="已抽取", en_evidence="已抽取", zh_line=0, en_line=0, anchor="全文",
        )]

    # 句对级视图数据：给前端「并排对照」用。每对带是否命中问题的标记，
    # 让用户直观看到「哪句对哪句、哪句有差异」，而不只是摘要表。
    segment_pairs: list[dict[str, Any]] = []
    issue_blob = json.dumps(final_rows, ensure_ascii=False)
    for block in aligned:
        for pair in block["pairs"]:
            hit = pair["cn"][:40] in issue_blob or pair["en"][:40] in issue_blob
            segment_pairs.append({
                "anchor": block["key"],
                "cn": pair["cn"],
                "en": pair["en"],
                "cn_line": pair["cn_line"],
                "en_line": pair["en_line"],
                "status": "diff" if hit else "same",
            })

    return {
        "rows": final_rows,
        "segment_pairs": segment_pairs,
        "layer_stats": {
            "aligned_blocks": len(aligned),
            "aligned_pairs": sum(len(b["pairs"]) for b in aligned),
            "deterministic": len(det_rows),
            "semantic": len(sem_rows),
            "final": len(final_rows),
        },
    }
