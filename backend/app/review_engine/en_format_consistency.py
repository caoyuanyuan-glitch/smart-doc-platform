"""英文确定性格式规则（DET-EN 系列）。

来源：T7 EN R03 Tina 批注对照差距分析（2026-11-24）——39 条人工批注中
平台漏报 18 条，其中可由文本层确定性规则补齐的部分集中在本模块。

覆盖 5 类（对应 T7 EN R03 漏报：页码粘连×3、货号×1、范围符×1、
华氏换算×10 处同错、负号疑多打×1）：
- DET-EN-PAGEGLUE      交叉引用页码与后词粘连（on page 164for ...）
- DET-EN-CATNO-FMT     货号位数偏离全文多数（46 处 6 位 vs 1 处 8 位）
- DET-EN-RANGE-SEP     数值范围分隔符 ~ 与 to 混用（少数派上报，挂人工）
- DET-EN-TEMP-CONVERT  ℃/℉ 对照换算算术校验（F = C×9/5 + 32）
- DET-EN-NEG-TEMP      个位数负温度疑多打负号（-2 ℃；冷库 -20/-80 不在此列）

设计原则同 cn_format_consistency.py：只报确定性事实或挂人工的少数派，
不做绝对化断言；验证语料为 T7 EN R03 全文（实测见测试用例注释）。
"""

from __future__ import annotations

import re

from app.review_engine.issue_position_utils import (
    build_context as _build_context,
    encode_position as _encode_position,
    page_at as _page_at,
)


def _issue(
    text: str,
    start: int,
    end: int,
    original: str,
    rule: str,
    category: str,
    description: str,
    suggestion: str,
    *,
    confidence: int,
    basis: str = "英文技术文档写作规范",
    needs_human_review: bool = False,
) -> dict:
    issue = {
        "severity": "general",
        "category": category,
        "rule": rule,
        "chapter": "",
        "original_text": original,
        "context": _build_context(text, start, end),
        "suggestion": suggestion,
        "description": description,
        "audit_basis": basis,
        "confidence": confidence,
        "source": "rule",
        "status": "open",
        "position": _encode_position(start, end, page=_page_at(text, start), area="正文"),
    }
    if needs_human_review:
        issue["needs_human_review"] = True
        position = issue["position"]
        if isinstance(position, str):
            import json as _json

            try:
                pos = _json.loads(position)
            except Exception:
                pos = {}
        else:
            pos = dict(position or {})
        pos["needs_human_review"] = True
        issue["position"] = (
            _json.dumps(pos, ensure_ascii=False) if isinstance(position, str) else pos
        )
    return issue


# ── 交叉引用页码粘连 ─────────────────────────────────────────────
# 「on page 164for buffer exchange」——页码引用后直接连字母。
# 限定 pages?/see 前缀，天然排除 25in（英寸）、2001to 等无关数字粘连。
_PAGEGLUE_RE = re.compile(r"\b(?:pages?|see)\s+(\d{1,3})((?:for|to|in|on))\b", re.IGNORECASE)


def check_page_reference_glued(text: str, *, parsed: bool = True) -> list[dict]:
    """页码引用与后词粘连上报（DET-EN-PAGEGLUE）。

    T7 EN R03 实测：全文 3 处命中（164for/164to/163in），零噪声。
    带空格的「page 16 to 20」是合法写法，不匹配。
    """
    source = str(text or "")
    if not parsed or not source.strip():
        return []
    issues = []
    for m in _PAGEGLUE_RE.finditer(source):
        issues.append(_issue(
            source, m.start(), m.end(), m.group(0), "DET-EN-PAGEGLUE", "交叉引用格式",
            "交叉引用页码与后面的单词直接粘连，缺一个空格。",
            f"建议在页码 {m.group(1)} 与 “{m.group(2)}” 之间添加空格。",
            confidence=88,
            basis="说明书审核能力补强方案 - 交叉引用页码粘连（T7 EN R03 p83/p141 实测）",
        ))
    return issues


# ── 货号位数偏离多数 ─────────────────────────────────────────────
_CATNO_RE = re.compile(r"\b\d{3}-(\d{6,9})\b(?!\d)")


def check_catalog_number_digits(text: str, *, parsed: bool = True) -> list[dict]:
    """货号位数偏离全文多数形态时上报（DET-EN-CATNO-FMT）。

    多数形态按「位数」统计（T7 EN R03 实测：46 处 940-6位 vs 1 处 940-8位）。
    不推断正确货号是什么——只指出位数偏离事实，具体数值须人工核对。
    """
    source = str(text or "")
    if not parsed or not source.strip():
        return []
    matches = list(_CATNO_RE.finditer(source))
    if len(matches) < 6:
        return []
    by_len: dict[int, list[re.Match]] = {}
    for m in matches:
        by_len.setdefault(len(m.group(1)), []).append(m)
    if len(by_len) < 2:
        return []
    majority_len = max(by_len, key=lambda k: len(by_len[k]))
    minority_lens = [k for k in by_len if k != majority_len and len(by_len[k]) <= 2]
    issues = []
    for k in minority_lens:
        for m in by_len[k]:
            issues.append(_issue(
                source, m.start(), m.end(), m.group(0), "DET-EN-CATNO-FMT", "货号写法",
                f"该货号数字段为 {k} 位（全文其余 {len(by_len[majority_len])} 处货号均为 "
                f"{majority_len} 位形态），位数与多数写法不一致。",
                "建议核对该货号是否多打/漏打了数字，或确属独立编号体系。",
                confidence=80,
                basis="说明书审核能力补强方案 - 货号格式一致性（T7 EN R03 p60 实测）",
            ))
    return issues


# ── 范围分隔符一致性 ─────────────────────────────────────────────
# 只报紧贴型（1~2、20%~80%）。带空格的「7 ~ 9」「26 ~ 40」多为界面参数回显
# （is set to 7 ~ 9），按界面文字照搬口径不报（T7 EN R03 实测 2 处均为 UI 回显）。
_TILDE_RANGE_RE = re.compile(r"\d{1,4}(?:\.\d+)?%?~\d{1,4}(?:\.\d+)?%?")
_TO_RANGE_RE = re.compile(r"\d(?:\.\d+)?%?\s+to\s+\d")


def check_range_separator_style(text: str, *, parsed: bool = True) -> list[dict]:
    """数值范围分隔符 ~ 与 to 混用时按少数派上报（DET-EN-RANGE-SEP，挂人工）。

    只报紧贴型 ~（1~2、20%~80%）；带空格的 ~ 多为界面参数回显，不报。
    T7 EN R03 实测：紧贴 ~ 2 处（1~2、20%~80%）vs 全文「to」31+ 处。
    """
    source = str(text or "")
    if not parsed or not source.strip():
        return []
    tildes = list(_TILDE_RANGE_RE.finditer(source))
    to_count = len(_TO_RANGE_RE.findall(source))
    if not tildes or to_count < 5 or to_count < len(tildes) * 4:
        return []
    issues = []
    for m in tildes:
        issues.append(_issue(
            source, m.start(), m.end(), m.group(0), "DET-EN-RANGE-SEP", "数值范围写法",
            f"数值范围分隔符使用「~」，与全文多数写法（{to_count} 处「to」）不一致。",
            "建议改为「to」（如 20% to 80%），与全文写法统一；请人工确认。",
            confidence=70,
            needs_human_review=True,
            basis="说明书审核能力补强方案 - 范围分隔符一致性（T7 EN R03 p224 实测）",
        ))
    return issues


# ── ℃/℉ 对照换算校验 ────────────────────────────────────────────
_DEG_C = r"(?:\u2103|\u00b0\s?C)"
_DEG_F = r"\u00b0\s?F"
_NUM = r"(-?\d+(?:\.\d+)?)"
_TEMP_PAIR_RE = re.compile(
    _NUM + r"\s?" + _DEG_C + r"\s+to\s+" + _NUM + r"\s?" + _DEG_C
    + r"[^()]{0,30}?\(\s*" + _NUM + r"\s?" + _DEG_F + r"\s+to\s+"
    + _NUM + r"\s?" + _DEG_F + r"\s*\)"
)
_F_TOLERANCE = 1.0  # 容忍舍入误差（35.6/46.4 这类 0.1 位换算值）


def check_temperature_conversion(text: str, *, parsed: bool = True) -> list[dict]:
    """℃/℉ 对照范围换算算术校验（DET-EN-TEMP-CONVERT）。

    提取「X ℃ to Y ℃ (A °F to B °F)」对照对，按 F = C×9/5 + 32 核验，
    容差 ±1.0 ℉。T7 EN R03 实测：31 对正确、10 对换算错误
    （同一处 2 ℃→(59 ℉ to 86 ℉) 错误在全文重复出现）。
    """
    source = str(text or "")
    if not parsed or not source.strip():
        return []
    issues = []
    for m in _TEMP_PAIR_RE.finditer(source):
        c1, c2, f1, f2 = (float(g) for g in m.groups())
        e1, e2 = c1 * 9 / 5 + 32, c2 * 9 / 5 + 32
        if abs(e1 - f1) <= _F_TOLERANCE and abs(e2 - f2) <= _F_TOLERANCE:
            continue
        snippet = m.group(0).strip()
        issues.append(_issue(
            source, m.start(), m.end(), snippet, "DET-EN-TEMP-CONVERT", "数值正确性",
            f"华氏温度与摄氏温度换算不一致：{c1} ℃≈{round(e1, 1)} ℉、{c2} ℃≈{round(e2, 1)} ℉，"
            f"文中写作 ({f1} ℉ to {f2} ℉)。",
            f"建议按 F = C×9/5 + 32 核对并更正华氏数值（预期 {round(e1, 1)} ℉ to {round(e2, 1)} ℉），并全文通查同表写法。",
            confidence=92,
            basis="说明书审核能力补强方案 - 温标换算算术校验（T7 EN R03 p60 实测）",
        ))
    return issues


# ── 个位数负温度疑多打负号 ────────────────────────────────────────
_NEG_TEMP_RE = re.compile(r"(?<![\d.])-([1-5])(\.\d+)?\s?(?:\u2103|\u00b0\s?C)")


def check_suspicious_negative_temperature(text: str, *, parsed: bool = True) -> list[dict]:
    """个位数负温度挂人工确认（DET-EN-NEG-TEMP）。

    -2 ℃ 这类个位数负温度常见于「2 ℃」前误敲负号（冷库常用温度是
    -20 ℃/-80 ℃ 两位数，冷藏区间为 2 ℃~8 ℃），但 -4 ℃ 等确有合法使用
    场景（如部分低温保存液），故只挂人工不定级。
    T7 EN R03 实测：1 处命中（p63「-2 ℃ to 8 ℃」，人工裁定应为 2 ℃）。
    """
    source = str(text or "")
    if not parsed or not source.strip():
        return []
    issues = []
    for m in _NEG_TEMP_RE.finditer(source):
        snippet = source[m.start():m.end()]
        issues.append(_issue(
            source, m.start(), m.end(), snippet, "DET-EN-NEG-TEMP", "数值正确性",
            "出现个位数负温度（-1 ℃~ -5 ℃）。冷藏/常温区间通常不含负值，"
            "负号可能为误敲（如 2 ℃ 误写为 -2 ℃）；低温冷库常用 -20 ℃/-80 ℃ 不受影响。",
            "请人工核对该负号是否多余（对照上下文的储存/运输温度要求）。",
            confidence=70,
            needs_human_review=True,
            basis="说明书审核能力补强方案 - 负温度合理性（T7 EN R03 p63 实测）",
        ))
    return issues


def check_en_format_consistency(text: str, *, parsed: bool = True) -> list[dict]:
    """DET-EN 系列总入口。"""
    issues: list[dict] = []
    for fn in (
        check_page_reference_glued,
        check_catalog_number_digits,
        check_range_separator_style,
        check_temperature_conversion,
        check_suspicious_negative_temperature,
    ):
        issues.extend(fn(text, parsed=parsed))
    return issues
