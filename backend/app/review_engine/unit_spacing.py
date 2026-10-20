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


def _encode_position(start: int, end: int, **meta) -> str:
    payload = {"start": start, "end": end, "area": meta.pop("area", "正文")}
    payload.update({key: value for key, value in meta.items() if value not in (None, "", [], {})})
    return json.dumps(payload, ensure_ascii=False)


def _page_at(text: str, offset: int) -> int:
    return text[: max(0, offset)].count("\f") + 1


def _context(text: str, start: int, end: int, radius: int = 60) -> str:
    return re.sub(r"\s+", " ", text[max(0, start - radius):min(len(text), end + radius)]).strip()


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
        # 跳过已被上一行拆开的情形（换行不是"缺空格"，是折行）。
        prefix = source[max(0, start - 1):start]
        if prefix in {"\n", "\f", " "}:
            continue
        issues.append(_issue(
            "DET-SPACE-GAP", source, start, match.end(), source[start - 1:match.end()],
            f"数值与单位之间缺少空格。全文同类写法中，带空格 {spaced} 处、"
            f"紧贴 {tight} 处，本处属于少数写法。",
            "建议按全文多数写法，在数值与单位之间补一个空格。",
        ))
        reported += 1
        if reported >= 5:
            break
    return issues


def check_units_and_spacing(text: str, *, parsed: bool = True) -> list[dict]:
    """数值-单位写法与间距检查入口。"""
    issues = check_unit_consistency(text, parsed=parsed)
    issues.extend(check_number_unit_spacing(text, parsed=parsed))
    return issues
