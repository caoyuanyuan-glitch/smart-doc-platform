# -*- coding: utf-8 -*-
"""渲染层字符裁剪检测：单位尾字符存在于文本层但页面未渲染（DET-CN-UNITTRUNC 渲染通道）。

背景（2026-11-24 园园对 T7RS R02 #15/#16 的裁定）：p180/p181 图注 P5 行
「引物工作液1.8 m」不是「mL 缺空格」，而是可见文字少了 L（应为 1.8 mL）。

取证结论（重要，别再按「纯文本缺字」处理）：
- PDF 内容流里其实写的是 `1.8 mL`，但 L 字符被裁剪路径切掉，渲染页不显示；
- 平台 document_parser 用 `get_text("dict", flags=TEXT_PRESERVE_WHITESPACE)`
  （不裁剪）→ document.content 读到的是 `1.8 mL`，文本层规则看不到缺陷；
- PyMuPDF 默认提取（`get_text()` / rawdict，带 MEDIABOX_CLIP）会丢掉被裁剪
  字符 → 读到 `1.8 m`，与用户所见一致。

因此本模块对同一页做两种 flags 的 rawdict 比对：文本层含 `数值 + mL`、
但默认（可见）提取缺尾字符 L 时上报。零模型依赖、纯 fitz 几何。

守卫（防噪声）：
  1. 只认体积单位 mL/µL/μL 的尾字符 L；
  2. 同页可见文本中同数值的完整 `mL` 写法 ≥2 处（同族多数形态确立）；
  3. 尾字符按 (x0, y0, 字符) 在可见提取中出现 → 已渲染，不报。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterator

import fitz

# 数值 + m + 尾字符 L/l（尾字符即疑似被裁剪者）
_CLIPPED_UNIT_RE = re.compile(r"(?P<num>\d+(?:\.\d+)?)\s*m(?P<tail>[Ll])(?![A-Za-z])")
# 同页可见完整写法计数（按数值）
_VISIBLE_FULL_RE = re.compile(r"(?P<num>\d+(?:\.\d+)?)\s*(?:mL|µL|μL)(?![A-Za-z])")

_CATEGORY = "数值与单位写法"
_BASIS = "中文技术文档写作规范 - 单位完整性（渲染层可见文本）"


def _iter_line_chars(raw: dict) -> Iterator[list[dict]]:
    for block in raw.get("blocks") or []:
        if block.get("type") != 0:
            continue
        for line in block.get("lines") or []:
            chars = [c for span in line.get("spans") or [] for c in span.get("chars") or []]
            if chars:
                yield chars


def _char_key(c: dict) -> tuple:
    bbox = c.get("bbox") or (0, 0, 0, 0)
    return (round(float(bbox[0]), 1), round(float(bbox[1]), 1), c.get("c", ""))


def _scan_page(raw_full: dict, raw_visible: dict, page_number: int) -> list[dict]:
    """比对同页两种提取结果，返回渲染层缺 L 的 issue 列表（纯函数，便于测试）。"""
    visible_keys = {_char_key(c) for chars in _iter_line_chars(raw_visible) for c in chars}
    visible_lines = ["".join(c.get("c", "") for c in chars) for chars in _iter_line_chars(raw_visible)]
    full_counts: dict[str, int] = {}
    for line in visible_lines:
        for m in _VISIBLE_FULL_RE.finditer(line):
            num = m.group("num")
            full_counts[num] = full_counts.get(num, 0) + 1

    issues: list[dict] = []
    seen: set[tuple] = set()
    for chars in _iter_line_chars(raw_full):
        s = "".join(c.get("c", "") for c in chars)
        for m in _CLIPPED_UNIT_RE.finditer(s):
            num = m.group("num")
            siblings = full_counts.get(num, 0)
            if siblings < 2:
                continue  # 同页未确立完整单位的多数写法，不下结论
            tail_idx = m.end("tail") - 1
            if tail_idx >= len(chars):
                continue
            if _char_key(chars[tail_idx]) in visible_keys:
                continue  # 尾字符确实渲染了，不是裁剪
            key = (num, s[:m.start("num")][-20:])
            if key in seen:
                continue
            seen.add(key)
            visible_text = s[:m.start("num")] + num + " m"
            issues.append({
                "severity": "general",
                "category": _CATEGORY,
                "rule": "DET-CN-UNITTRUNC",
                "chapter": "",
                "original_text": f"{num} m",
                "context": visible_text[-100:].strip(),
                "suggestion": f"建议核对可见文字，补 L 改为「{num} mL」。",
                "description": (
                    f"页面可见文字为「{num} m」，疑似单位缺 L（应为 {num} mL）；"
                    f"PDF 文本层虽含「{num} mL」，但尾字符 L 被裁剪未渲染，"
                    f"同页另有 {siblings} 处可见的完整写法。属渲染层差异，文本层规则无法发现。"
                ),
                "audit_basis": _BASIS,
                "confidence": 85,
                "source": "rule",
                "status": "open",
                "position": {
                    "page_number": page_number,
                    "start": -1,
                    "end": -1,
                    "area": "正文",
                },
            })
    return issues


def detect_clipped_unit_chars(pdf_path: str | Path) -> list[dict]:
    """扫描 PDF：文本层含 mL 但渲染缺 L 时上报（DET-CN-UNITTRUNC）。"""
    issues: list[dict] = []
    try:
        doc = fitz.open(str(pdf_path))
    except Exception:
        return issues
    try:
        with doc:
            for pno, page in enumerate(doc, start=1):
                try:
                    # 与 document_parser.extract_pdf 完全一致的 flags（不裁剪）
                    raw_full = page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
                    # 默认 flags 带 MEDIABOX_CLIP，与页面可见文字一致
                    raw_visible = page.get_text("rawdict")
                except Exception:
                    continue
                issues.extend(_scan_page(raw_full, raw_visible, pno))
    except Exception:
        return issues
    return issues
