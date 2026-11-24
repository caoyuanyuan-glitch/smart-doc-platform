"""PDF 表格连续性几何规则（DET-VIS 系列，纯 fitz 信号，不依赖视觉模型 key）。

背景（2026-11-23 P2 视觉通道）：T7 R01 goldset 漏报中「表头行没有跨页重复」
类 2 条（p69/p84）属几何可检信号——上页底部表格与本页顶部表格构成跨页续表，
但续页未重复表头行。

实现要点（稳定性教训）：
- PyMuPDF find_tables 的**行列内容提取**在同一文档上多次运行结果不同（同一页
  首行内容三次运行三种结果），不能用做判定依据；但**表格 bbox 几何**与
  **clip 区域文本**（page.get_text(clip=...)）跨运行稳定。因此只用 find_tables
  定位表格 bbox，全部内容判定基于 clip 文本的行序列。
- clip 行序列 = clip 区域文本按内容流分行（norm 去空白）。真实 PDF 与合成
  PDF 中表格 cell 文本均为一行/cell，口径一致。

判定口径（全部满足才报，宁缺勿滥）：
1. 本页第一个表格 bbox 顶部 y0 < 160pt（贴页顶）；
2. 上一页最后一个表格 bbox 底部 y1 > 页高-170pt（贴页底）；
3. 上一页底表下方无正文块（页眉 y<60、纯数字页码除外）；
4. 本页顶表上方无正文块（同上）——有表题（如「表 43 …」）即视为独立表格，不报；
5. 表头重复判定：上页底表 clip 首行出现在续页顶表 clip 前 3 行中 → 已重复，不报
   （T7 实证：p28/p57/p119 的相邻独立/续表均重复表头，由此拦下）；
6. 表头样抑制：续页顶表前 min(len(P),4) 行全部「无数字且 <8 字符」→ 视为
   列名行而非数据行（相邻独立表格），不报。

置信度 72（suggestion 级挂人工确认）：几何信号只证明「存在贴顶贴底的表格对」，
不证明「续页一定缺表头」。
"""

from __future__ import annotations

import re
from pathlib import Path

from app.review_engine.issue_position_utils import encode_position as _encode_position

RULE_ID = "DET-VIS-TABLE-CONT-001"

_TOP_Y_MAX_PT = 160.0        # 本页首表贴页顶阈值
_BOTTOM_Y_MIN_PT = 170.0     # 上页末表贴页底阈值（页高-pt）
_HEADER_Y_MAX_PT = 60.0      # 页眉区
_HEADER_LOOKAHEAD = 3        # 表头重复判定的续页行前视窗口
_HEADER_LIKE_MAX_ROWS = 4    # 表头样抑制的比对行数上限
_HEADER_LIKE_MAX_CHARS = 8   # 「短列名」长度上限
_PAGE_NO_RE = re.compile(r"^\d{1,3}$")
_ROMAN_PAGE_RE = re.compile(r"^[ivxlIVXL]+$")
_DIGIT_RE = re.compile(r"\d")


def _norm(s: str | None) -> str:
    return re.sub(r"\s+", "", s or "")


def _clip_lines(page, bbox) -> list[str]:
    """clip 区域文本按内容流分行（norm、去空行）。跨运行稳定。"""
    try:
        text = page.get_text("text", clip=bbox)
    except Exception:
        return []
    lines = []
    for line in (text or "").splitlines():
        normed = _norm(line)
        if normed:
            lines.append(normed)
    return lines


def _body_blocks(page, y_max: float | None = None) -> list[str]:
    """正文文本块（滤页眉、纯数字/罗马页码）。"""
    out: list[str] = []
    for block in page.get_text("blocks") or []:
        y1 = float(block[3])
        if y_max is not None and y1 > y_max:
            continue
        text = str(block[4]).strip().replace("\n", " ")
        if not text or y1 < _HEADER_Y_MAX_PT:
            continue
        if _PAGE_NO_RE.fullmatch(text) or _ROMAN_PAGE_RE.fullmatch(text):
            continue
        out.append(text)
    return out


def _safe_tables(page) -> list:
    try:
        return list(page.find_tables().tables)
    except Exception:
        return []


def _issue(page_number: int, clip_text: str) -> dict:
    clipped = re.sub(r"\s+", " ", clip_text).strip()
    return {
        "severity": "suggestion",
        "category": "表格规范",
        "rule": RULE_ID,
        "chapter": "",
        "original_text": clipped[:80],
        "context": clipped[:400],
        "suggestion": "疑似跨页表格未在续页重复表头行，请人工确认；若确为续表，建议设置表头行跨页重复。",
        "description": (
            "上一页底部表格与本页顶部表格构成跨页续表，但续页表格开头未出现上一页的表头行，"
            "可能缺少跨页重复表头（几何信号，置信度有限，请人工确认）。"
        ),
        "audit_basis": "PDF 几何信号——跨页表格表头连续性检测（T7 R01 goldset p69/p84 实证）",
        "confidence": 72,
        "source": "rule",
        "status": "open",
        "position": _encode_position(0, 0, page=page_number, area="表格"),
    }


def check_pdf_table_continuity(pdf_path: str | Path) -> list[dict]:
    """扫描 PDF，报「跨页续表未重复表头行」疑点。解析失败返回空列表。"""
    path = Path(pdf_path)
    if not path.exists():
        return []
    try:
        import fitz
    except ModuleNotFoundError:
        return []

    issues: list[dict] = []
    try:
        doc = fitz.open(str(path))
    except Exception:
        return []
    try:
        for index in range(1, doc.page_count):
            page = doc[index]
            tables = _safe_tables(page)
            if not tables:
                continue
            first = min(tables, key=lambda t: t.bbox[1])
            if first.bbox[1] >= _TOP_Y_MAX_PT:
                continue
            prev = doc[index - 1]
            prev_tables = _safe_tables(prev)
            if not prev_tables:
                continue
            prev_last = max(prev_tables, key=lambda t: t.bbox[3])
            if prev_last.bbox[3] <= prev.rect.height - _BOTTOM_Y_MIN_PT:
                continue
            # 上页底表下方、本页顶表上方都不允许有正文（页眉/页码除外）
            below_body = False
            for block in prev.get_text("blocks") or []:
                if float(block[1]) > prev_last.bbox[3] + 2:
                    text = str(block[4]).strip().replace("\n", " ")
                    if text and float(block[3]) > _HEADER_Y_MAX_PT and not _PAGE_NO_RE.fullmatch(text):
                        below_body = True
                        break
            if below_body:
                continue
            if _body_blocks(page, first.bbox[1] - 2):
                continue
            cur_bbox = fitz.Rect(*first.bbox)
            prev_bbox = fitz.Rect(*prev_last.bbox)
            prev_rows = _clip_lines(prev, prev_bbox)
            cur_rows = _clip_lines(page, cur_bbox)
            if not cur_rows:
                continue
            # 表头重复：上页底表首行出现在续页顶表前几行中 → 已重复，不报
            if prev_rows and prev_rows[0] in cur_rows[:_HEADER_LOOKAHEAD]:
                continue
            # 表头样抑制：续页开头几行全是短列名（无数字、<8 字符）→ 独立表格，不报
            head = cur_rows[: min(len(prev_rows) or _HEADER_LIKE_MAX_ROWS, _HEADER_LIKE_MAX_ROWS)]
            if head and all(not _DIGIT_RE.search(line) and len(line) < _HEADER_LIKE_MAX_CHARS for line in head):
                continue
            issues.append(_issue(index + 1, page.get_text("text", clip=cur_bbox) or cur_rows[0]))
    finally:
        doc.close()
    return issues
