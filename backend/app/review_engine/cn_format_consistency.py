"""中文确定性格式规则（DET-CN 系列）。

设计原则（承接 unit_spacing.py 的少数派样式思路）：
1. 只报「同一文档内多数写法已确立，少数写法偏离」的确定性事实，
   不做绝对化断言（避免把全篇一致的风格当错误刷噪声）。
2. 每条规则必须在真实 goldset（T7 R01 41 条人工批注）上验证过，
   且全文扫描确认误报面可控后才收录。

覆盖 5 类（对应 T7 R01 goldset 漏报 #3/#4/#6/#10/#15/#33）：
- DET-CN-UNITSPACE   数字与摄氏度紧贴（多数写法带空格时）
- DET-CN-CATNO-FMT   货号格式偏离多数（如 940-00317100 缺尾段，多数为 940-XXXXXX-XX）
- DET-CN-REDUNDANT   「超过…以上」语义重复
- DET-CN-PUNCT-CLUSTER 冒号后紧跟逗号（如「处理：，以下」）
- DET-CN-LINE-LEAD   行首标点（避头尾；常为换行/表格断行残留，置信度压到 70 交人工确认）
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
    basis: str = "中文技术文档写作规范",
) -> dict:
    return {
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


# 数字紧贴摄氏度（digit 与 ℃/°C 之间无空格）。℃ U+2103 会被 NFKC 展开成 °C，
# 两种码位都要覆盖（见 unit_spacing.py 文件头说明）。
_TIGHT_DEG_RE = re.compile(r"\d(?:\.\d+)?(?:℃|°C)")
_SPACED_DEG_RE = re.compile(r"\d(?:\.\d+)?\s+(?:℃|°\s?C)")

# 货号：标准形态 前段-6位-2位；偏离形态 前段-7或8位（无尾段）。
_STD_CATNO_RE = re.compile(r"\b\d{3}-\d{6}-\d{2}\b")
_DEV_CATNO_RE = re.compile(r"\b\d{3}-\d{7,8}\b(?!\-\d)")

# 「超过 N 天/小时…以上」语义重复。
_REDUNDANT_OVER_RE = re.compile(r"超过[^。！？\n]{1,12}?以上")

# 冒号后紧跟逗号（全/半角冒号 × 逗号）。
_COLON_COMMA_RE = re.compile(r"[：:]\s*[，,]")

# 行首标点（避头尾）；缩进含全角空格。
_LINE_LEAD_PUNCT_RE = re.compile(r"(?m)^[ \t\u3000]*[，。；、]")


def check_tight_degree_unit(text: str, *, parsed: bool = True) -> list[dict]:
    """数字与 ℃ 紧贴、且全文多数写法带空格时上报（DET-CN-UNITSPACE）。

    只报少数派：紧贴数 ≥1 且（带空格数 ≥5 且 带空格数 ≥ 紧贴数×4）。
    全文一致紧贴时不报（风格统一，不属于确定性错误）。
    """
    source = str(text or "")
    if not parsed or not source.strip():
        return []
    spaced = list(_SPACED_DEG_RE.finditer(source))
    tight = list(_TIGHT_DEG_RE.finditer(source))
    if not tight or len(spaced) < 5 or len(spaced) < len(tight) * 4:
        return []
    issues = []
    for m in tight:
        issues.append(_issue(
            source, m.start(), m.end(), m.group(0), "DET-CN-UNITSPACE", "数值与单位写法",
            "数字与摄氏度之间缺少空格，与全文多数写法（数字与 ℃ 间留空格）不一致。",
            "建议在数字与 ℃ 之间添加空格，与全文写法统一。",
            confidence=84,
            basis="数字与单位书写规范 - 温度单位",
        ))
    return issues


def check_catalog_number_format(text: str, *, parsed: bool = True) -> list[dict]:
    """货号格式偏离全文多数写法时上报（DET-CN-CATNO-FMT）。

    多数形态为 `前段-6位-尾段`（如 940-001530-00）而个别写成
    `前段-7或8位`（缺尾段，如 940-00317100）时，报「格式偏离，建议核对」。
    不推断正确货号是什么——只指出偏离事实，具体数值须人工核对。
    """
    source = str(text or "")
    if not parsed or not source.strip():
        return []
    std_count = len(_STD_CATNO_RE.findall(source))
    if std_count < 5:
        return []
    issues = []
    for m in _DEV_CATNO_RE.finditer(source):
        issues.append(_issue(
            source, m.start(), m.end(), m.group(0), "DET-CN-CATNO-FMT", "货号写法",
            f"该货号缺少尾段（全文其余 {std_count} 处货号均为「前段-6位-尾段」形态），格式与多数写法不一致。",
            "建议核对该货号是否缺尾段（如应为 XXXXXX-XX 形态）或为独立编号体系。",
            confidence=80,
            basis="说明书审核能力补强方案 - 货号格式一致性",
        ))
    return issues


def check_redundant_over_above(text: str, *, parsed: bool = True) -> list[dict]:
    """「超过…以上」语义重复上报（DET-CN-REDUNDANT）。

    「超过 5 天以上」中「超过」与「以上」语义重叠，二选一即可。
    """
    source = str(text or "")
    if not parsed or not source.strip():
        return []
    issues = []
    for m in _REDUNDANT_OVER_RE.finditer(source):
        issues.append(_issue(
            source, m.start(), m.end(), m.group(0), "DET-CN-REDUNDANT", "重复内容",
            "「超过」与「以上」语义重复，二者保留其一即可。",
            "建议删除「以上」（如改为「超过 5 天未使用」），或删除「超过」。",
            confidence=90,
            basis="中文技术文档写作规范 - 语义重复",
        ))
    return issues


def check_colon_comma(text: str, *, parsed: bool = True) -> list[dict]:
    """冒号后紧跟逗号上报（DET-CN-PUNCT-CLUSTER）。

    「……处理：，以下步骤……」——冒号后不应直接接逗号，
    通常应删除冒号（冒号引出的应是列表/正文而非逗号）。
    """
    source = str(text or "")
    if not parsed or not source.strip():
        return []
    issues = []
    for m in _COLON_COMMA_RE.finditer(source):
        issues.append(_issue(
            source, m.start(), m.end(), m.group(0), "DET-CN-PUNCT-CLUSTER", "标点符号",
            "冒号后紧跟逗号，标点叠用。",
            "建议删除冒号（冒号后直接接正文），或删除逗号后补充冒号应引出的内容。",
            confidence=92,
            basis="中文技术文档写作规范 - 标点叠用",
        ))
    return issues


def check_line_leading_punct(text: str, *, parsed: bool = True) -> list[dict]:
    """行首标点上报（DET-CN-LINE-LEAD，避头尾）。

    行首出现 ，。；、 属排版残留（多余回车/断行），置信度压到 70
    自动挂 needs_human_review——文本层命中可能来自表格解析顺序，须人工目检。
    """
    source = str(text or "")
    if not parsed or not source.strip():
        return []
    issues = []
    for m in _LINE_LEAD_PUNCT_RE.finditer(source):
        snippet = source[m.start():m.start() + 12].strip()
        issues.append(_issue(
            source, m.start(), min(len(source), m.start() + 8), snippet or m.group(0).strip(),
            "DET-CN-LINE-LEAD", "标点符号",
            "行首出现标点符号，不符合避头尾规则，通常是标点前存在多余回车/断行。",
            "建议检查该行标点前的断行，将标点回收到上一行行尾。",
            confidence=70,
            basis="中文排版规范 - 避头尾",
        ))
    return issues


def check_cn_format_consistency(text: str, *, parsed: bool = True) -> list[dict]:
    """DET-CN 系列总入口。"""
    issues: list[dict] = []
    for fn in (
        check_tight_degree_unit,
        check_catalog_number_format,
        check_redundant_over_above,
        check_colon_comma,
        check_line_leading_punct,
    ):
        issues.extend(fn(text, parsed=parsed))
    return issues
