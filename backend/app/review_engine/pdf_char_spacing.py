# -*- coding: utf-8 -*-
"""渲染层字符间距检测：数字-单位渲染紧贴但文本层带空格（DET-CN-UNITSPACE 补充通道）。

背景（2026-11-24 园园裁定）：`54 min`、`300 bp` 在 PDF 文本层带空格（提取器按
字符间距补的），渲染页面上实际紧贴——纯文本层比对判不出来。但字符坐标本身
就在 PDF 内容流里，属于纯文本可判信息：用 PyMuPDF rawdict 的字符 bbox 检测
「数字与单位首字符之间无空白字符（内容流紧贴）且渲染 gap 极小」的词，报
DET-CN-UNITSPACE。

判定两条件（同时满足）：
  1. 内容流紧贴：数字末字符与单位首字符之间无空格字符（正则匹配天然保证）；
  2. 渲染紧贴：gap = 单位首字符 x0 - 数字末字符 x1 < 0.2 × 字号。
     内容流里作者用字符间距拉开视觉空格的不报（gap ≥ 阈值）。

不调任何模型，纯 fitz 几何，PDF 文件专用。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import fitz

# 数字 + 单位（内容流紧贴才可能命中；单位词后不能再跟字母，防 domain/2hatch 误吃）
_UNIT_RE = re.compile(
    r"(\d+(?:\.\d+)?)(min|bp|kb|mL|µL|μL|GB|TB|MB|KB|h)(?![A-Za-z])"
)

# 渲染紧贴阈值：相对字号的比例。正常字符间距 ≈0.05–0.12 em；
# 文本层 "54 min" 的空格宽度 ≈0.25–0.35 em。取 0.2 折中。
_TIGHT_GAP_RATIO = 0.2

_CATEGORY = "数值与单位写法"
_BASIS = "数字与单位书写规范 - 数字与单位间需留空格"


def _check_line(chars: list[dict], page_number: int, issues: list[dict]) -> None:
    s = "".join(c.get("c", "") for c in chars)
    if not s:
        return
    for m in _UNIT_RE.finditer(s):
        digits_end = m.start(1) + len(m.group(1))  # 数字末字符在 s 中的下一位
        c1 = chars[digits_end - 1]
        c2 = chars[digits_end]
        size1 = float(c1.get("size") or 0) or 10.0
        x1 = float(c1.get("bbox")[2])
        x0 = float(c2.get("bbox")[0])
        gap = x0 - x1
        if gap >= _TIGHT_GAP_RATIO * size1:
            continue  # 渲染上有空格感（作者用字符定位拉开），不报
        matched = m.group(0)
        issues.append({
            "severity": "general",
            "category": _CATEGORY,
            "rule": "DET-CN-UNITSPACE",
            "chapter": "",
            "original_text": matched,
            "context": s[max(0, m.start() - 30):m.end() + 30].replace("\n", " "),
            "suggestion": f"建议在数字与 {m.group(2)} 之间添加空格。",
            "description": (
                f"数字与单位 {m.group(2)} 在页面上实际紧贴（文本层因字符定位被补了空格），"
                "与数字与单位间需留空格的规范不符。"
            ),
            "audit_basis": _BASIS,
            "confidence": 82,
            "source": "rule",
            "status": "open",
            "position": {
                "page_number": page_number,
                "start": -1,
                "end": -1,
                "area": "正文",
            },
        })


def detect_render_tight_units(pdf_path: str | Path) -> list[dict]:
    """扫描 PDF 渲染层：数字与单位渲染紧贴时上报（DET-CN-UNITSPACE）。"""
    issues: list[dict] = []
    try:
        doc = fitz.open(str(pdf_path))
    except Exception:
        return issues
    try:
        with doc:
            for pno, page in enumerate(doc, start=1):
                try:
                    raw = page.get_text("rawdict")
                except Exception:
                    continue
                for block in raw.get("blocks") or []:
                    if block.get("type") != 0:
                        continue
                    for line in block.get("lines") or []:
                        chars = [
                            c
                            for span in line.get("spans") or []
                            for c in span.get("chars") or []
                        ]
                        if len(chars) < 3:
                            continue
                        _check_line(chars, pno, issues)
    except Exception:
        return issues
    return issues
