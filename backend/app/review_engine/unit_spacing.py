"""数值-单位写法一致性检查（DET-SPACE 系列）。

为什么单独成文件：
1) `℃`(U+2103) 与 `°C`(U+2100 + 'C') 在视觉上几乎相同，但码位不同。
   NFKC 归一化会把 U+2103 展开成 `°C`，因此**任何只写 `℃` 的正则，
   在归一化文本上必然 100% 漏检**。本模块的匹配式一律同时覆盖两种码位。
2) 「数字与单位之间必须有空格」不是通用规则：`5%`、`10^6L`、`1M`、`0V`
   紧贴才是正确写法。只按「紧贴即报错」实现会产生大量误报，故本模块
   只上报**同一文档内同一部件单位写法不一致**这一确定性事实。
"""

from __future__ import annotations

import json
import re


# 单位写法变体：同一物理单位在正文中的不同书写。
# key 是归一化后的「单位身份」，value 是允许的书写形态（正则片段）。
_UNIT_FORMS: dict[str, str] = {
    "degc": r"(?:℃|°\s*C)",
    "degf": r"℉",
    "celsius": r"Celsius",
    "percent": r"%",
    "microlitre": r"(?:μL|µL|uL)",
    "millilitre": r"mL",
    "rpm": r"rpm",
}

# 数值后紧跟单位、但缺少空格的形态。
# 注意排除 %（百分号紧贴是正确写法）与数量级前缀（M/m/u/k/n/μ）。
_NUM_UNIT_NOSPACE_RE = re.compile(
    r"(?<=\d)"
    r"(?:"
    r"℃|°\s*C"
    r"|mL|mg|ng|kg|μL|µL|uL|nm|μg|µg|mm|cm|km|μm|µm"
    r"|rpm|min|sec|Hz|kHz|mA|kV|bar|psi"
    r")"
)


from app.review_engine.issue_position_utils import (
    encode_position as _encode_position,
    page_at as _page_at,
    build_context as _build_context,
)


def _context(text: str, start: int, end: int, radius: int = 60) -> str:
    return _build_context(text, start, end, radius)


def _issue(rule, text, start, end, original, description, suggestion, *, chapter=""):
    return {
        "severity": "general",
        "category": "数值与单位写法",
        "rule": rule,
        "chapter": chapter,
        "original_text": original,
        "context": _context(text, start, end),
        "suggestion": suggestion,
        "description": description,
        "audit_basis": "数值与单位书写规范",
        "confidence": 82,
        "source": "rule",
        "status": "pending",
        "position": _encode_position(start, end, page=_page_at(text, start), area="正文"),
    }


def check_unit_consistency(text: str, *, parsed: bool = True) -> list[dict]:
    """同一文档内数值-单位写法不一致时上报（DET-SPACE-UNIT）。

    只报可确定性判定的两类：
    1. 温度单位码位混用（`℃` 与 `°C` 并存）；
    2. 同一单位的不同书写形式并存（如 `μL` 与 `uL`、`℃` 与 `Celsius`）。
    """
    source = str(text or "")
    if not parsed or not source.strip():
        return []

    issues = []

    # --- 1) 温度单位码位混用 -------------------------------------------
    # 必须在原始文本上统计，不能用 NFKC 归一化后的文本：归一化会抹平差异。
    single = len(re.findall(r"℃", source))
    degree = len(re.findall(r"°\s*C", source))
    if single and degree:
        majority = "℃" if single >= degree else "°C"
        other = "°C" if majority == "℃" else "℃"
        for match in re.finditer(r"℃" if other == "℃" else r"°\s*C", source):
            issues.append(_issue(
                "DET-SPACE-UNIT", source, match.start(), match.end(), match.group(0),
                f"全文温度单位混用：`℃` 出现 {single} 次，`°C` 出现 {degree} 次。"
                f"两种写法视觉接近但码位不同，跨系统复制或字体替换时易丢失单位。",
                f"建议统一为 {majority}。",
            ))
            break  # 同类问题只报首处，避免逐条刷屏

    # --- 2) 同一单位多种书写形式并存 ------------------------------------
    for identity, form in _UNIT_FORMS.items():
        variants: dict[str, int] = {}
        for variant_re in re.finditer(form, source):
            key = re.sub(r"\s+", "", variant_re.group(0))
            variants[key] = variants.get(key, 0) + 1
        # 只有一种写法即无问题；°C/℃ 的重复情形已在第 1 项处理。
        if len(variants) < 2:
            continue
        if identity in {"degc", "degf"}:
            continue  # 温度码位混用已单独处理，避免重复上报
        majority = max(variants, key=lambda key: variants[key])
        for variant, count in variants.items():
            if variant == majority:
                continue
            match = re.search(form, source)
            if not match:
                continue
            issues.append(_issue(
                "DET-SPACE-UNIT", source, match.start(), match.end(), match.group(0),
                f"同一单位存在多种书写形式：{'、'.join(f'{k}({v}次)' for k, v in sorted(variants.items(), key=lambda kv: -kv[1]))}。"
                "单位书写不统一会影响检索与跨文档比对。",
                f"建议统一为 {majority}（全文出现 {variants[majority]} 次）。",
            ))
            break

    return issues


_PART_NO_TAIL_RE = re.compile(r"[A-Za-z0-9\-_.]*$")


def _is_inside_part_number(source: str, start: int) -> bool:
    """判断匹配点是否落在货号/型号内部（如 `71474-1L`、`S128511-1L` 的 `1L`）。

    判据：左侧同一词片段含连字符且存在 ≥3 位连续数字组。
    不要求含字母——本仓真实货号是纯数字型 `71474-1L`；
    也刻意排除 `20-30` 这类量程（两个 2 位数），避免把正常写法漏报。
    """
    left = source[max(0, start - 32):start]
    match = _PART_NO_TAIL_RE.search(left)
    if not match:
        return False
    token = match.group(0)
    return "-" in token and bool(re.search(r"\d{3,}", token))


def _number_start(source: str, unit_start: int) -> int:
    """从单位字符向左回退，取到完整数值的起点。

    正则用零宽后顾 `(?<=\\d)` 匹配单位，`match.start()` 落在单位字符上，
    只回退 1 位只能拿到 `0℃`；必须回退整个数字串才得到 `40℃`。
    """
    i = unit_start
    while i > 0 and (source[i - 1].isdigit() or source[i - 1] in ".,"):
        i -= 1
    return i


def check_number_unit_spacing(text: str, *, parsed: bool = True) -> list[dict]:
    """数值与单位之间缺少空格的孤立写法（DET-SPACE-GAP）。

    仅在**多数写法正确、少数漏空格**时报出，即以全文众数为准；
    若全文均为紧贴（如通篇 `5%`）则判定为该文档的既定风格，不报。
    """
    source = str(text or "")
    if not parsed or not source.strip():
        return []

    spaced = len(re.findall(rf"\d+[ \t]+(?:mL|mg|ng|kg|nm|mm|cm|rpm|min|Hz)", source))
    tight = len(_NUM_UNIT_NOSPACE_RE.findall(source))
    if not tight or not spaced:
        return []
    if tight >= spaced:
        # 紧贴占多数，属既定书写风格。
        return []

    issues = []
    reported = 0
    for match in _NUM_UNIT_NOSPACE_RE.finditer(source):
        start = match.start()
        span_start = _number_start(source, start)
        if span_start >= start:
            # 单位前没有数字，不是「数值+单位」，不报。
            continue
        # 只跳过换行/换页造成的折行；行内空格是正常上下文，不能跳
        # （`then 5mL` 正是要报的少数派写法）。
        if source[max(0, span_start - 1):span_start] in {"\n", "\f"}:
            continue
        if _is_inside_part_number(source, span_start):
            continue
        issues.append(_issue(
            "DET-SPACE-GAP", source, span_start, match.end(), source[span_start:match.end()],
            f"数值与单位之间缺少空格。全文同类写法中，带空格 {spaced} 处、"
            f"紧贴 {tight} 处，本处属于少数写法。",
            "建议按全文多数写法，在数值与单位之间补一个空格。",
        ))
        reported += 1
        if reported >= 5:
            break
    return issues


# 人工主流报「单位前缺空格」的安全单位：紧贴即可报，不含 % / M / μ。
# 顺序要求：复合单位必须排在单单位前面，否则 "5mL/min" 会被 mL 抢先匹配掉。
# 注意：分支末尾不能留空 "|"，(?:a|b|) 会匹配空串，导致每个数字后都产出一条 issue。
_SAFE_TIGHT_UNIT_RE = re.compile(
    r"(?<=\d)(?:"
    r"mL/min|mL/h|L/min|L/h|"
    r"℃|°\s*C|"
    r"mL|µL|uL|"
    r"rpm|"
    r"VDC|VAC|VA|kW|mW|"
    r"mA|µA|uA|mV|kV|"
    r"Hz|kHz|MHz|"
    r"kg|mg|µg|ug|"
    r"kPa|MPa|bar|"
    r"mm|cm|nm|bp|"
    r"min|sec|"
    r"L|V|A|W|g|N|Pa|s"
    r")(?![A-Za-z])"
)


def check_safe_tight_unit_gap(text: str, *, parsed: bool = True) -> list[dict]:
    """对安全单位表上报数值紧贴单位的孤立写法（DET-SPACE-GAP）。"""
    source = str(text or "")
    if not parsed or not source.strip():
        return []
    issues = []
    for match in _SAFE_TIGHT_UNIT_RE.finditer(source):
        start = match.start()
        span_start = _number_start(source, start)
        if span_start >= start:
            continue
        if source[max(0, span_start - 1):span_start] in {"\n", "\f"}:
            continue
        # 货号 `71474-1L` 的 `1L` 不是「数值+单位」，补空格会把货号改坏。
        if _is_inside_part_number(source, span_start):
            continue
        issues.append(_issue(
            "DET-SPACE-GAP", source, span_start, match.end(), source[span_start:match.end()],
            "数值与单位之间缺少空格。本规范要求数值与单位分开写。",
            "建议在数值与单位之间补一个空格。",
        ))
        if len(issues) >= 5:
            break
    return issues


def check_units_and_spacing(text: str, *, parsed: bool = True) -> list[dict]:
    """数值-单位写法与间距检查入口。"""
    issues = check_unit_consistency(text, parsed=parsed)
    issues.extend(check_number_unit_spacing(text, parsed=parsed))
    seen = {(item.get("rule"), item.get("original_text"), item.get("position")) for item in issues}
    for item in check_safe_tight_unit_gap(text, parsed=parsed):
        key = (item.get("rule"), item.get("original_text"), item.get("position"))
        if key in seen:
            continue
        issues.append(item)
        seen.add(key)
    return issues
