"""PDF layout geometry signals for visual-candidate ranking only.

Constraint C3: these scores may rank pages, attach diagnostics, or seed
manual-review hints. They must not emit high-confidence true positives.
"""

from __future__ import annotations

from pathlib import Path


THICK_LINE_PT = 1.8


def _line_gaps(page) -> list[float]:
    gaps = []
    try:
        data = page.get_text("dict") or {}
    except Exception:
        return gaps
    ys = []
    for block in data.get("blocks") or []:
        for line in block.get("lines") or []:
            bbox = line.get("bbox") or (0, 0, 0, 0)
            ys.append(float(bbox[1]))
    ys.sort()
    for index in range(1, len(ys)):
        gap = ys[index] - ys[index - 1]
        if 0.5 < gap < 80:
            gaps.append(gap)
    return gaps


def _drawing_widths(page) -> list[float]:
    widths = []
    try:
        drawings = page.get_drawings() or []
    except Exception:
        return widths
    for drawing in drawings:
        width = drawing.get("width")
        if width is None:
            continue
        try:
            widths.append(abs(float(width)))
        except (TypeError, ValueError):
            continue
    return widths


def _image_offset_ratio(page) -> float:
    rect = page.rect
    page_cx = (rect.x0 + rect.x1) / 2.0
    page_cy = (rect.y0 + rect.y1) / 2.0
    width = max(float(rect.width or 1.0), 1.0)
    height = max(float(rect.height or 1.0), 1.0)
    best = 0.0
    try:
        data = page.get_text("dict") or {}
    except Exception:
        return 0.0
    for block in data.get("blocks") or []:
        if int(block.get("type") or 0) != 1:
            continue
        bbox = block.get("bbox") or (0, 0, 0, 0)
        cx = (float(bbox[0]) + float(bbox[2])) / 2.0
        cy = (float(bbox[1]) + float(bbox[3])) / 2.0
        offset = abs(cx - page_cx) / width + abs(cy - page_cy) / height
        if offset > best:
            best = offset
    return round(best, 4)


def collect_page_layout_signals(page) -> dict:
    gaps = _line_gaps(page)
    widths = _drawing_widths(page)
    median_gap = sorted(gaps)[len(gaps) // 2] if gaps else 0.0
    crowding = 0.0
    if median_gap:
        crowding = max(0.0, min(1.0, (14.0 - median_gap) / 10.0))
    thick = sum(1 for width in widths if width >= THICK_LINE_PT)
    thick_ratio = (thick / len(widths)) if widths else 0.0
    return {
        "drawing_line_count": len(widths),
        "thick_line_count": thick,
        "thick_line_ratio": round(thick_ratio, 4),
        "line_gap_median": round(median_gap, 2),
        "crowding_score": round(crowding, 4),
        "image_offset_ratio": _image_offset_ratio(page),
    }


def collect_pdf_layout_signals(file_path: str | Path) -> dict[int, dict]:
    """Return 1-based page_number -> signal dict. Empty on parse failure."""
    path = Path(file_path)
    if not path.exists():
        return {}
    try:
        import fitz
    except ModuleNotFoundError:
        return {}
    signals = {}
    try:
        with fitz.open(str(path)) as doc:
            for index, page in enumerate(doc, start=1):
                signals[index] = collect_page_layout_signals(page)
    except Exception:
        return {}
    return signals


def layout_candidate_score(candidate: dict) -> tuple:
    signals = candidate.get("layout_signals") or {}
    reasons = {str(item) for item in (candidate.get("reasons") or [])}
    return (
        1 if "dense_table_or_layout" in reasons else 0,
        1 if reasons.intersection({"table_layout", "layout_keyword"}) else 0,
        int(candidate.get("table_blocks") or 0),
        int(signals.get("drawing_line_count") or 0),
        float(signals.get("crowding_score") or 0.0),
        float(signals.get("thick_line_ratio") or 0.0),
        float(signals.get("image_offset_ratio") or 0.0),
        len(candidate.get("reasons") or []),
        -int(candidate.get("page_number") or 0),
    )
