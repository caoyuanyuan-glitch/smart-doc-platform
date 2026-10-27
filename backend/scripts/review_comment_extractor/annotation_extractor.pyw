#!pythonw
# -*- coding: utf-8 -*-
"""Self-contained Windows UI for extracting PDF/Word review comments.

Double-click 打开审核意见汇总工具.vbs (preferred) or this .pyw file.
Do not double-click a .py file: Windows will attach a console that looks
like PowerShell and may loop on Microsoft Store python stubs.
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import traceback
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path


WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
APP_TITLE = "人工审核意见汇总工具"
EMPTY_SELECTED = "（空——批注覆盖在图上/线框区域，无文本层）"


def hide_windows_console():
    """Detach any console created by double-clicking a .py file."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        hwnd = kernel32.GetConsoleWindow()
        if hwnd:
            user32.ShowWindow(hwnd, 0)
            kernel32.FreeConsole()
    except Exception:
        pass


def crash_log_path():
    return Path(__file__).resolve().with_name("annotation_extractor_error.log")


def write_crash_log(text):
    try:
        crash_log_path().write_text(text, encoding="utf-8")
    except Exception:
        pass


def launch_log_path():
    return Path(__file__).resolve().with_name("annotation_extractor_launch.log")


def append_launch_log(text):
    try:
        with launch_log_path().open("a", encoding="utf-8") as handle:
            handle.write(text if str(text).endswith("\n") else str(text) + "\n")
    except Exception:
        pass


def show_native_message(title, text, error=True):
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, str(text), str(title), 0x10 if error else 0x40)
        return True
    except Exception:
        return False


def show_startup_error(exc):
    detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    write_crash_log(detail)
    append_launch_log(f"startup error: {exc}\n{detail}")
    if show_native_message("启动失败", f"{exc}\n\n详细错误已写入：\n{crash_log_path()}"):
        return
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("启动失败", f"{exc}\n\n详细错误已写入：\n{crash_log_path()}")
    except Exception:
        pass


def clean(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


CJK_CHAR = re.compile(r"[\u3400-\u9fff\u3040-\u30ff\uff00-\uffef]")
HEADING_LINE = re.compile(r"^\d+(?:\.\d+){0,3}\s+\S")
MARKUP_TYPES = {"Highlight", "Underline", "StrikeOut", "Squiggly"}
CONTEXT_MAX_CHARS = 420
MARKER_TYPES = {"Square", "Circle", "Text", "FreeText", "Caret", "Note", "Stamp", "Ink"}
REPLACE_RE = re.compile(
    r"^(?P<src>.+?)\s*(?:改成|改为|换成|应改为|应为|→|->)\s*(?P<dst>.+)$"
)
VISUAL_KW = re.compile(
    r"列宽|分布|留白|空隙|太近|隔开|距离|对齐|错位|多余|重叠|挤压|"
    r"换行|字号|加粗|图标|居中|线|图|颜色|边距|突出|缩进|格式"
)
TEXTUAL_KW = re.compile(
    r"中英文不一致|不一致|重复|页码|索引|错字|错别字|缺字|漏字|"
    r"有没有|是否|需要|应改为|改成|术语|翻译|单位|序号|编号|内容|文字|"
    r"逗号|句号|双引号|引号|冒号|空格|标点|括号|分号|破折号|"
    r"拼写|拼错|spell|typo|"
    r"冠词|形容词|介词|单复数|语法|"
    r"改为|建议改|缺|缺失|少|增加|加上|冗余|去掉|删除|"
    r"特殊字符|乱码|不显示|异常显示"
)


def _median(values):
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return 0
    mid = len(vals) // 2
    if len(vals) % 2:
        return vals[mid]
    return (vals[mid - 1] + vals[mid]) / 2


def _is_cjk(ch):
    return bool(ch) and CJK_CHAR.match(ch) is not None


def _as_float(value, default=0.0):
    if isinstance(value, bool) or value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    return default


def _flatten_xy_numbers(obj, out):
    if obj is None or isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        out.append(float(obj))
        return
    if hasattr(obj, "x") and hasattr(obj, "y"):
        out.append(_as_float(obj.x))
        out.append(_as_float(obj.y))
        return
    if isinstance(obj, (tuple, list)):
        for item in obj:
            _flatten_xy_numbers(item, out)


def _as_rect(box):
    import fitz

    if box is None:
        return None
    if isinstance(box, fitz.Rect):
        return box
    try:
        if hasattr(box, "x0") and hasattr(box, "y0"):
            return fitz.Rect(box)
    except Exception:
        pass
    nums = []
    _flatten_xy_numbers(box, nums)
    if len(nums) >= 4:
        return fitz.Rect(nums[0], nums[1], nums[2], nums[3])
    return None


def join_fragments(parts):
    pieces = [part for part in parts if part]
    if not pieces:
        return ""
    text = pieces[0]
    for part in pieces[1:]:
        if not text:
            text = part
            continue
        if _is_cjk(text[-1]) or _is_cjk(part[0]) or text[-1] in "，。；：、,.!?;:":
            text += part
        else:
            text += " " + part
    return clean(text)


def strip_bullet_junk(text):
    text = str(text or "")
    text = re.sub(r"^[ylnuYLNU•·●○■□▪▫◆◇►‣]\s*(?=[\u3400-\u9fff])", "", text)
    text = re.sub(r"^[•·●○■□▪▫◆◇►‣]\s*", "", text)
    text = re.sub(r"^[ylnu]\s+(?=[A-Z])", "", text)
    return text.strip()


def clean_block(text):
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in str(text or "").splitlines()]
    return "\n".join(line for line in lines if line)


def is_junk_span(span):
    text = clean(span.get("text"))
    font = (span.get("font") or "").lower()
    if any(key in font for key in ("dingbat", "wingding", "webding", "symbol", "zapf")):
        return True
    if not text:
        return True
    if len(text) == 1 and text.lower() in "ylnu":
        return True
    if len(text) == 1 and (not _is_cjk(text)) and (not text.isalnum()):
        return True
    return False


def is_margin_marker(annot):
    typ = annot.type[1] if getattr(annot, "type", None) else ""
    if typ in MARKUP_TYPES:
        return False
    if typ in MARKER_TYPES:
        rect = _as_rect(getattr(annot, "rect", None))
        if rect is None:
            return True
        return rect.width < 90 or rect.height < 28
    return True


def looks_like_noise_selected(selected, sentence=""):
    selected = clean(selected)
    if not selected:
        return True
    if len(selected) <= 2 and not any(_is_cjk(ch) for ch in selected):
        return True
    collapsed_sentence = (sentence or "").replace(" ", "")
    collapsed_selected = selected.replace(" ", "")
    if collapsed_sentence and collapsed_selected not in collapsed_sentence and len(selected) <= 8:
        return True
    return False


def interpret_change(selected, comment, sentence=""):
    selected = clean(selected)
    comment = clean(comment)
    if looks_like_noise_selected(selected, sentence):
        selected = ""
    original = selected or first_original_line(sentence)
    if not comment:
        return f"原文：{original or '-'}\n意见：（空）"

    match = REPLACE_RE.match(comment)
    if match:
        return f"把「{clean(match.group('src'))}」改成「{clean(match.group('dst'))}」"

    if re.search(r"删掉|删除|去掉", comment):
        extra = f"\n涉及原文：{original}" if original else ""
        return f"{comment}{extra}"

    if re.search(r"空格|空行|多余|少了|多了|漏了|逗号|句号|错别字", comment):
        return f"{comment}\n对照原文：{original or '-'}"

    if selected and selected != comment:
        return f"把原文「{selected}」按意见修改：{comment}"

    if original:
        return f"在原文标注处按意见处理：{comment}\n原文：{original}"
    return comment


def first_original_line(sentence):
    block = clean_block(sentence)
    if not block:
        return ""
    return block.splitlines()[0]


def mark_snippet(text, selected):
    block = clean_block(text)
    selected = clean(selected)
    if selected and selected in block:
        return block.replace(selected, f"【{selected}】", 1)
    return block


def useful_selected(selected, sentence, marker):
    selected = clean(selected)
    if not selected:
        return ""
    if looks_like_noise_selected(selected, sentence):
        return ""
    return selected


def markup_rects(annot):
    import fitz

    flat = []
    _flatten_xy_numbers(getattr(annot, "vertices", None) or [], flat)
    points = [(flat[i], flat[i + 1]) for i in range(0, len(flat) // 2 * 2, 2)]
    rects = []
    for i in range(0, len(points) // 4 * 4, 4):
        quad = points[i:i + 4]
        try:
            rects.append(fitz.Quad(quad).rect)
        except Exception:
            xs = [p[0] for p in quad]
            ys = [p[1] for p in quad]
            rects.append(fitz.Rect(min(xs), min(ys), max(xs), max(ys)))
    if not rects:
        fallback = _as_rect(getattr(annot, "rect", None))
        if fallback is None:
            return []
        rects.append(fallback)
    return [rect + (-1.5, -1.5, 1.5, 1.5) for rect in rects]


def box_hits_rects(box, rects):
    import fitz

    box = _as_rect(box)
    if box is None or box.is_empty or box.is_infinite:
        return False
    box_area = box.width * box.height
    for rect in rects:
        rect = _as_rect(rect)
        if rect is None:
            continue
        inter = box & rect
        if inter.is_empty or inter.width < 0.6 or inter.height < 0.6:
            continue
        if box_area <= 0:
            return True
        if (inter.width * inter.height) / box_area >= 0.2 or inter.width >= min(2.5, box.width * 0.5):
            return True
    return False


def collect_spans(page):
    import fitz

    spans = []
    payload = page.get_text("dict")
    for block_no, block in enumerate(payload.get("blocks", [])):
        if block.get("type", 0) != 0:
            continue
        for line_no, line in enumerate(block.get("lines", [])):
            for span_no, span in enumerate(line.get("spans", [])):
                text = span.get("text") or ""
                if not clean(text):
                    continue
                bbox = _as_rect(span.get("bbox"))
                if bbox is None:
                    continue
                spans.append({
                    "text": text,
                    "bbox": bbox,
                    "size": _as_float(span.get("size")),
                    "font": span.get("font") or "",
                    "block": block_no,
                    "line": line_no,
                    "span": span_no,
                    "y0": bbox.y0,
                    "y1": bbox.y1,
                })
    return spans


def selected_from_chars(page, rects):
    import fitz

    payload = page.get_text("rawdict")
    fragments = []
    buf = []
    for block in payload.get("blocks", []):
        if block.get("type", 0) != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                chars = span.get("chars")
                if not chars:
                    text = span.get("text") or ""
                    if text and box_hits_rects(span.get("bbox"), rects):
                        fragments.append(text)
                    continue
                for char in chars:
                    glyph = char.get("c") or ""
                    if glyph and box_hits_rects(char.get("bbox"), rects):
                        buf.append(glyph)
                    elif buf:
                        fragments.append("".join(buf))
                        buf = []
                if buf:
                    fragments.append("".join(buf))
                    buf = []
    if buf:
        fragments.append("".join(buf))
    return join_fragments(fragments)


def is_heading_span(span, body_size):
    text = clean(span["text"])
    if body_size and span["size"] >= body_size * 1.15 + 0.4:
        return True
    return bool(HEADING_LINE.match(text) and len(text) <= 40)


def nearest_span_ids(spans, rect, max_dist=40):
    import fitz

    rect = _as_rect(rect)
    if rect is None:
        return []
    cx = (rect.x0 + rect.x1) / 2
    cy = (rect.y0 + rect.y1) / 2
    best_ids = []
    best_dist = max_dist
    for i, span in enumerate(spans):
        box = span["bbox"]
        dx = 0 if box.x0 <= cx <= box.x1 else min(abs(cx - box.x0), abs(cx - box.x1))
        dy = 0 if box.y0 <= cy <= box.y1 else min(abs(cy - box.y0), abs(cy - box.y1))
        dist = (dx * dx + dy * dy) ** 0.5
        if dist < best_dist - 0.4:
            best_dist = dist
            best_ids = [i]
        elif abs(dist - best_dist) <= 0.4:
            best_ids.append(i)
    return best_ids


def pointed_span_ids(spans, rect, max_dist=120):
    rect = _as_rect(rect)
    if rect is None:
        return []
    scored = []
    ry = (rect.y0 + rect.y1) / 2
    for i, span in enumerate(spans):
        if is_junk_span(span):
            continue
        box = span["bbox"]
        cy = (box.y0 + box.y1) / 2
        dy = abs(cy - ry)
        if dy > 40:
            continue
        if box.x1 < rect.x0 - 8:
            dx = rect.x0 - box.x1 + 40
        elif box.x0 > rect.x1 + 8:
            dx = box.x0 - rect.x1
        else:
            dx = 0
        length_bonus = min(len(clean(span["text"])), 24) * 0.15
        scored.append((dy + dx * 0.35 - length_bonus, i))
    if not scored:
        return nearest_span_ids(spans, rect, max_dist=max_dist)
    scored.sort()
    best = scored[0][0]
    hits = [i for dist, i in scored if dist <= best + 4]
    long_hits = [i for i in hits if len(clean(spans[i]["text"])) >= 3]
    return long_hits or hits


def group_line_ids(spans):
    groups = []
    current_key = None
    current = []
    for i, span in enumerate(spans):
        key = (span["block"], span["line"])
        if key != current_key:
            if current:
                groups.append(current)
            current_key = key
            current = [i]
        else:
            current.append(i)
    if current:
        groups.append(current)
    return groups


def line_text_from_ids(spans, ids):
    parts = []
    for i in ids:
        if is_junk_span(spans[i]):
            continue
        parts.append(spans[i]["text"])
    return strip_bullet_junk(join_fragments(parts))


def context_view(spans, hit_ids):
    if not spans or not hit_ids:
        return "", "", ""
    groups = group_line_ids(spans)
    hit = min(hit_ids)
    gindex = 0
    for gi, group in enumerate(groups):
        if hit in group:
            gindex = gi
            break

    hits = [spans[i] for i in hit_ids]
    body_size = _median([span["size"] for span in hits]) or 11
    line_h = _median([span["bbox"].height for span in hits]) or 12
    lo = hi = gindex
    heading_idx = None
    heading_above = False

    def bundled_len(left, right):
        return sum(len(line_text_from_ids(spans, groups[k])) for k in range(left, right + 1))

    def gap_groups(left, right):
        return max(0.0, spans[groups[right][0]]["y0"] - spans[groups[left][-1]]["y1"])

    while lo > 0:
        prev = spans[groups[lo - 1][0]]
        heading = is_heading_span(prev, body_size) or is_heading_span(
            spans[groups[lo - 1][-1]], body_size
        )
        if heading:
            if heading_above:
                break
            lo -= 1
            heading_idx = lo
            heading_above = True
            continue
        if gap_groups(lo - 1, lo) > line_h * 1.8:
            break
        if prev["size"] > body_size + 2.5:
            break
        lo -= 1
        if bundled_len(lo, hi) >= CONTEXT_MAX_CHARS:
            lo += 1
            break

    while hi < len(groups) - 1:
        nxt = spans[groups[hi + 1][0]]
        if is_heading_span(nxt, body_size):
            break
        if gap_groups(hi, hi + 1) > line_h * 1.8:
            break
        if nxt["size"] > body_size + 2.5:
            break
        hi += 1
        if bundled_len(lo, hi) >= CONTEXT_MAX_CHARS:
            hi -= 1
            break

    lines = [line_text_from_ids(spans, groups[k]) for k in range(lo, hi + 1)]
    lines = [line for line in lines if line]
    heading = line_text_from_ids(spans, groups[heading_idx]) if heading_idx is not None else ""
    sentence = line_text_from_ids(spans, groups[gindex])
    return heading, sentence, "\n".join(lines)


def extract_comment_view(page, annot):
    try:
        rects = markup_rects(annot)
        typ = annot.type[1] if annot.type else ""
        spans = collect_spans(page)
        marker = is_margin_marker(annot)
        hit_ids = [i for i, span in enumerate(spans) if box_hits_rects(span["bbox"], rects)]
        if (not hit_ids) or marker:
            pointed = pointed_span_ids(spans, annot.rect)
            if pointed:
                hit_ids = pointed

        selected = ""
        if not marker:
            selected = selected_from_chars(page, rects)
            if not selected and hit_ids:
                selected = join_fragments(
                    [spans[i]["text"] for i in hit_ids if not is_junk_span(spans[i])]
                )
            if not selected:
                selected = strip_bullet_junk(clean(page.get_textbox(annot.rect)))

        heading, sentence, context = context_view(spans, hit_ids)
        if not context:
            context = sentence or selected
        selected = useful_selected(selected, sentence or context, marker)
        comment = clean((annot.info or {}).get("content"))
        return {
            "selected": selected,
            "heading": heading,
            "sentence": sentence,
            "context": context,
            "change": interpret_change(selected, comment, sentence or context),
        }
    except Exception:
        try:
            selected = clean(page.get_textbox(annot.rect))
        except Exception:
            selected = ""
        comment = ""
        try:
            comment = clean((annot.info or {}).get("content"))
        except Exception:
            pass
        return {
            "selected": selected,
            "heading": "",
            "sentence": selected,
            "context": selected,
            "change": interpret_change(selected, comment, selected),
        }


def extract_selected_and_context(page, annot):
    view = extract_comment_view(page, annot)
    context = view["context"]
    if view["heading"] and view["heading"] not in context:
        context = view["heading"] + "\n" + context
    return view["selected"], context


def format_annot_rect(annot):
    try:
        r = annot.rect
        return f"({r.x0:.1f}, {r.y0:.1f}, {r.x1:.1f}, {r.y1:.1f})"
    except Exception:
        return ""


def short_prefix(pdf):
    """截图文件名前缀：有货号用货号；无货号用完整文件名（去扩展名），保证可读且尽量唯一。"""
    match = re.search(r"H-\d{3}-\d{6}-\d{2}", Path(pdf).name)
    return match.group(0) if match else Path(pdf).stem


def allocate_prefix(pdf, used):
    """分配本轮唯一的截图前缀：撞名自动加 _2/_3 后缀。"""
    base = short_prefix(pdf)
    if base not in used:
        used.add(base)
        return base
    n = 2
    while f"{base}_{n}" in used:
        n += 1
    used.add(f"{base}_{n}")
    return f"{base}_{n}"


def save_annot_shot(page, annot, out_dir, idx, prefix):
    """渲染批注区域及上下文为 JPEG；区域过小无意义。返回文件名，失败返回空串。"""
    try:
        import fitz

        out_dir.mkdir(parents=True, exist_ok=True)
        r = annot.rect
        pad_x = max(120, r.width * 2.0)
        pad_y = max(120, r.height * 2.0)
        clip = fitz.Rect(r.x0 - pad_x, r.y0 - pad_y, r.x1 + pad_x, r.y1 + pad_y) & page.rect
        scale = max(1.2, min(2.0, 450 / max(min(clip.width, clip.height), 1)))
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=clip, colorspace=fitz.csRGB)
        name = f"{prefix}_p{page.number + 1}_ann{idx}.jpg"
        pix.save(str(out_dir / name), jpg_quality=82)
        return name
    except Exception:
        return ""


def is_visual_annot(page, annot, selected, comment):
    """意见双向判定：视觉词→图；文本词→免图；无法判断→按覆盖兜底"""
    c = comment or ""
    if VISUAL_KW.search(c):
        return True
    if TEXTUAL_KW.search(c):
        return False
    if not (selected or "").strip():
        return True
    return False


def has_comment(row):
    comment = clean(row.get("comment"))
    return bool(comment and comment != "-")


def input_files(path):
    path = Path(path)
    if path.is_dir():
        return sorted(
            file for file in path.rglob("*")
            if file.is_file() and file.suffix.lower() in {".pdf", ".docx"} and not file.name.startswith("~$")
        )
    return [path] if path.is_file() else []


def markdown_files(path):
    path = Path(path)
    if path.is_dir():
        return sorted(
            file for file in path.rglob("*.md")
            if file.is_file() and not file.name.startswith("~$")
        )
    return [path] if path.is_file() and path.suffix.lower() == ".md" else []


def collect_shot_dirs(root):
    """取输入根目录下的统一截图目录（根目录/批注截图）"""
    root = Path(root)
    if root.is_file():
        root = root.parent
    shot_dir = root / "批注截图"
    return [shot_dir] if shot_dir.exists() else []


def pack_output(md_path, shot_dirs, root_name, max_bytes=30 * 1024 * 1024):
    """打包 md + 截图；按文件粒度切段，保证每个 zip <= max_bytes。
    zip 内第一层 = 最上层文件夹名（root_name），其下 md + 批注截图/。"""
    md_path = Path(md_path)
    top = root_name or "批注截图汇总"
    entries = []
    for shot_dir in shot_dirs:
        if shot_dir.exists():
            for shot in sorted(shot_dir.rglob("*.jpg")):
                entries.append((shot_dir, shot))

    batches, cur, cur_size = [], [], md_path.stat().st_size
    for entry in entries:
        size = entry[1].stat().st_size
        if cur and cur_size + size > max_bytes:
            batches.append(cur)
            cur, cur_size = [], md_path.stat().st_size
        cur.append(entry)
        cur_size += size
    if cur:
        batches.append(cur)

    zip_paths = []
    for i, batch in enumerate(batches, 1):
        zip_path = md_path.with_suffix(f".part{i}.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(md_path, f"{top}/{md_path.name}")
            for _shot_dir, shot in batch:
                zf.write(shot, f"{top}/批注截图/{shot.name}")
        zip_paths.append(zip_path)
    return zip_paths


def extract_pdf(pdf, root_dir, prefix=None, errors=None):
    try:
        import fitz
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "缺少 PyMuPDF 依赖。\n\n"
            "请打开“命令提示符”（cmd），运行：\n"
            "py -m pip install PyMuPDF\n\n"
            "不要打开 PowerShell 脚本，也不要使用 Microsoft Store 的 Python 占位程序。"
        ) from exc

    rows = []
    try:
        doc = fitz.open(pdf)
    except Exception as exc:
        raise RuntimeError(f"无法读取 PDF：{pdf}\n{exc}") from exc

    shot_dir = Path(root_dir) / "批注截图"
    prefix = prefix or short_prefix(pdf)
    with doc:
        for page_no, page in enumerate(doc, start=1):
            annot = page.first_annot
            while annot:
                try:
                    info = annot.info or {}
                    comment = clean(info.get("content"))
                    if not has_comment({"comment": comment}):
                        annot = annot.next
                        continue
                    view = extract_comment_view(page, annot)
                    annot_type = annot.type[1] if annot.type else "?"
                    idx = len(rows) + 1
                    filename = (
                        save_annot_shot(page, annot, shot_dir, idx, prefix)
                        if is_visual_annot(page, annot, view["selected"], comment)
                        else ""
                    )
                    shot = f"批注截图/{filename}" if filename else ""
                    rows.append({
                        "file": Path(pdf).name,
                        "page": page_no,
                        "type": annot_type,
                        "author": clean(info.get("title")),
                        "comment": comment,
                        "selected": view["selected"],
                        "heading": view["heading"],
                        "sentence": view["sentence"],
                        "context": view["context"],
                        "change": view["change"],
                        "rect": format_annot_rect(annot),
                        "shot": shot,
                    })
                except Exception as exc:
                    if errors is not None:
                        errors.append(f"{Path(pdf).name} p{page_no}: {exc}")
                annot = annot.next
    return rows


def xml_text(node):
    if node is None:
        return ""
    return clean("".join(text.text or "" for text in node.findall(".//w:t", WORD_NS)))


def extract_docx(docx, root_dir, errors=None):
    rows = []
    try:
        archive = zipfile.ZipFile(docx)
    except zipfile.BadZipFile:
        raise RuntimeError(f"无法读取 Word 文件：{docx}")

    with archive:
        names = set(archive.namelist())
        if "word/comments.xml" not in names:
            return rows

        comments_root = ET.fromstring(archive.read("word/comments.xml"))
        comments = {}
        for comment in comments_root.findall("w:comment", WORD_NS):
            comment_id = comment.attrib.get(f"{{{WORD_NS['w']}}}id", "")
            comments[comment_id] = {
                "author": comment.attrib.get(f"{{{WORD_NS['w']}}}author", ""),
                "comment": xml_text(comment),
            }

        selected_by_id = {}
        if "word/document.xml" in names:
            document_root = ET.fromstring(archive.read("word/document.xml"))
            active_id = None
            parts = []
            for elem in document_root.iter():
                tag = elem.tag.rsplit("}", 1)[-1]
                if tag == "commentRangeStart":
                    active_id = elem.attrib.get(f"{{{WORD_NS['w']}}}id", "")
                    parts = []
                elif tag == "t" and active_id is not None:
                    parts.append(elem.text or "")
                elif tag == "commentRangeEnd":
                    end_id = elem.attrib.get(f"{{{WORD_NS['w']}}}id", "")
                    if active_id == end_id:
                        selected_by_id[active_id] = clean("".join(parts))
                        active_id = None
                        parts = []

        for comment_id, data in comments.items():
            selected = selected_by_id.get(comment_id, "")
            comment = clean(data.get("comment"))
            rows.append({
                "file": Path(docx).name,
                "page": "-",
                "type": "WordComment",
                "author": clean(data.get("author")),
                "comment": comment,
                "selected": selected,
                "context": selected,
                "heading": "",
                "sentence": selected,
                "change": interpret_change(selected, comment, selected),
                "rect": "",
                "shot": "",
            })
    return rows


def extract_all(input_path):
    root = Path(input_path)
    if root.is_file():
        root = root.parent
    rows = []
    errors = []
    used_prefixes = set()
    files = input_files(input_path)
    if not files:
        raise RuntimeError("没有找到 PDF 或 Word（.docx）文件。请确认输入路径。")
    for file in files:
        suffix = file.suffix.lower()
        try:
            if suffix == ".pdf":
                prefix = allocate_prefix(file, used_prefixes)
                rows.extend(extract_pdf(file, root, prefix, errors))
            elif suffix == ".docx":
                rows.extend(extract_docx(file, root, errors))
        except Exception as exc:
            errors.append(f"{file.name}: {exc}")
    return [row for row in rows if has_comment(row)], errors


def parse_bullet(block, label):
    match = re.search(rf"^- {re.escape(label)}: (.*)$", block, flags=re.MULTILINE)
    return clean(match.group(1)) if match else ""


def parse_section(block, title):
    match = re.search(
        rf"^### {re.escape(title)}\s*\n(.*?)(?=^### |\n- 知识库整理:|\Z)",
        block,
        flags=re.MULTILINE | re.DOTALL,
    )
    return match.group(1).strip() if match else ""


def parse_markdown_file(md_file):
    text = Path(md_file).read_text(encoding="utf-8-sig")
    rows = []
    blocks = re.split(r"(?=^## \d+\. )", text, flags=re.MULTILINE)
    for block in blocks:
        header = re.search(r"^## \d+\. (.*?) · 第 (.*?) 页", block, flags=re.MULTILINE)
        if not header:
            continue
        row = {
            "file": clean(header.group(1)),
            "page": clean(header.group(2)),
            "type": parse_bullet(block, "批注类型"),
            "author": parse_bullet(block, "批注人"),
            "comment": parse_section(block, "人工意见") or parse_bullet(block, "人工意见"),
            "selected": parse_section(block, "批注覆盖文本") or parse_bullet(block, "选中文本"),
            "context": parse_section(block, "原文") or parse_bullet(block, "附近正文"),
            "heading": "",
            "sentence": "",
            "change": parse_section(block, "改什么"),
            "rect": parse_bullet(block, "批注矩形"),
            "shot": parse_bullet(block, "批注截图"),
        }
        if has_comment(row):
            rows.append(row)
    return rows


def merge_markdown(input_path):
    rows = []
    files = markdown_files(input_path)
    if not files:
        raise RuntimeError("没有找到 Markdown 文件。请确认输入路径。")
    for md_file in files:
        rows.extend(parse_markdown_file(md_file))
    return rows


def format_original(row):
    heading = clean(row.get("heading") or "")
    sentence = clean_block(row.get("sentence") or "")
    context = clean_block(row.get("context") or "")
    selected = row.get("selected") or ""
    body = context or sentence
    marked = mark_snippet(body, selected)
    parts = []
    if heading and heading not in marked:
        parts.append(f"【{heading}】")
    if marked:
        parts.append(marked)
    return "\n".join(parts).strip() or "-"


def format_selected_text(row):
    text = (row.get("selected") or "").strip()
    if not text or text == "-":
        return EMPTY_SELECTED
    return text


def to_markdown(rows):
    lines = ["# 人工审核 PDF 和 Word 批注汇总", ""]
    for i, row in enumerate(rows, start=1):
        comment = row.get("comment") or "-"
        lines += [
            f"## {i}. {row['file']} · 第 {row['page']} 页",
            "",
            f"- 批注人: {row['author'] or '-'}",
            f"- 批注类型: {row['type']}",
            f"- 批注矩形: {row.get('rect') or '-'}",
            f"- 批注截图: {row.get('shot') or '-'}",
            "",
            "### 批注覆盖文本",
            format_selected_text(row),
            "",
            "### 原文",
            format_original(row),
            "",
            "### 人工意见",
            comment,
            "",
        ]
    return "\n".join(lines)


def default_output(mode):
    return "全部人工审核意见汇总.md" if mode == "merge" else "人工审核意见汇总.md"


def normalize_output_path(folder, filename, mode="extract"):
    folder_text = str(folder or "").strip()
    name = str(filename or "").strip()
    folder_path = Path(folder_text) if folder_text else Path(".")

    def with_suffix(raw):
        raw = str(raw).strip()
        suffix = Path(raw).suffix.lower()
        if suffix in {".md", ".json"}:
            return raw
        return f"{raw}.md"

    if name:
        named = Path(name)
        if named.is_absolute():
            if named.exists() and named.is_dir():
                return named / default_output(mode)
            if named.suffix.lower() in {".md", ".json"}:
                return named
            return named.with_name(with_suffix(named.name))
        joined = folder_path / name
        if joined.exists() and joined.is_dir():
            return joined / default_output(mode)
        return folder_path / with_suffix(name)

    if folder_path.exists() and folder_path.is_file():
        return folder_path
    if folder_path.suffix.lower() in {".md", ".json"}:
        return folder_path
    return folder_path / default_output(mode)


def build_app():
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    class App(tk.Tk):
        def __init__(self):
            super().__init__()
            self.title(APP_TITLE)
            self.geometry("860x500")
            self.minsize(780, 460)
            self.resizable(True, True)
            self.mode = tk.StringVar(value="extract")
            self.input_path = tk.StringVar(value=str(Path.cwd()))
            self.output_path = tk.StringVar(value=str(Path.cwd() / default_output("extract")))
            self.status = tk.StringVar(value="选择输入/输出后点击开始汇总。")
            self.is_running = False
            self.protocol("WM_DELETE_WINDOW", self.close_window)
            self.build()

        def build(self):
            frame = ttk.Frame(self, padding=16)
            frame.pack(fill="both", expand=True)

            mode_frame = ttk.LabelFrame(frame, text="模式", padding=10)
            mode_frame.pack(fill="x")
            ttk.Radiobutton(
                mode_frame, text="提取 PDF/Word 批注", variable=self.mode,
                value="extract", command=self.refresh_output,
            ).pack(side="left", padx=(0, 24))
            ttk.Radiobutton(
                mode_frame, text="合并 Markdown", variable=self.mode,
                value="merge", command=self.refresh_output,
            ).pack(side="left")

            input_frame = ttk.LabelFrame(frame, text="输入", padding=10)
            input_frame.pack(fill="x", pady=(14, 0))
            ttk.Entry(input_frame, textvariable=self.input_path).pack(fill="x", expand=True)
            input_buttons = ttk.Frame(input_frame)
            input_buttons.pack(fill="x", pady=(8, 0))
            ttk.Button(input_buttons, text="选择文件夹", command=self.choose_input_folder).pack(side="left", padx=(0, 8))
            ttk.Button(input_buttons, text="选择单个文件", command=self.choose_input_file).pack(side="left")

            output_frame = ttk.LabelFrame(frame, text="输出", padding=10)
            output_frame.pack(fill="x", pady=(14, 0))
            out_row = ttk.Frame(output_frame)
            out_row.pack(fill="x")
            ttk.Label(out_row, text="输出文件", width=8).pack(side="left")
            ttk.Entry(out_row, textvariable=self.output_path).pack(
                side="left", fill="x", expand=True, padx=(0, 8)
            )
            ttk.Button(out_row, text="保存为", command=self.choose_output).pack(side="left")

            ttk.Label(
                output_frame,
                text="可直接修改文件名或完整路径，例如：人工审核意见汇总.md",
                foreground="#888888",
                font=("", 9),
            ).pack(anchor="w", pady=(4, 0))

            action_frame = ttk.Frame(frame)
            action_frame.pack(fill="x", pady=(20, 0))
            self.run_button = ttk.Button(action_frame, text="开始汇总", command=self.run)
            self.run_button.pack(side="left", ipadx=28, ipady=8)
            ttk.Label(action_frame, textvariable=self.status, anchor="w").pack(
                side="left", fill="x", expand=True, padx=(16, 0)
            )
            self.progress = ttk.Progressbar(frame, mode="indeterminate")
            self.progress.pack(fill="x", pady=(14, 0))

        def refresh_output(self):
            base = Path(self.input_path.get())
            folder = base if base.is_dir() else base.parent
            current = Path(self.output_path.get() or ".")
            defaults = {default_output("extract"), default_output("merge")}
            if (not current.name) or current.name in defaults:
                self.output_path.set(str(folder / default_output(self.mode.get())))

        def current_output_path(self):
            return Path(self.output_path.get())

        def choose_input_folder(self):
            selected = filedialog.askdirectory(initialdir=self.input_path.get() or str(Path.cwd()))
            if selected:
                self.input_path.set(selected)
                self.refresh_output()

        def choose_input_file(self):
            selected = filedialog.askopenfilename(
                initialdir=self.input_path.get() or str(Path.cwd()),
                filetypes=[("Supported files", "*.pdf *.docx *.md"), ("All files", "*.*")],
            )
            if selected:
                self.input_path.set(selected)
                self.refresh_output()

        def choose_output(self):
            selected = filedialog.asksaveasfilename(
                title="保存汇总到",
                initialdir=str(Path(self.output_path.get()).parent),
                initialfile=Path(self.output_path.get()).name,
                defaultextension=".md",
                filetypes=[("Markdown", "*.md"), ("所有文件", "*.*")],
            )
            if selected:
                self.output_path.set(selected)

        def run(self):
            if self.is_running:
                return
            output = self.current_output_path()
            if output.exists() and output.is_dir():
                messagebox.showerror(
                    "输出路径无效",
                    f"当前输出是文件夹，请填写文件名。\n\n{output}",
                )
                return
            if not output.parent.exists():
                messagebox.showerror(
                    "输出路径无效",
                    f"输出文件夹不存在：\n{output.parent}",
                )
                return
            self.is_running = True
            self.run_button.configure(state="disabled", text="正在汇总...")
            self.status.set("正在处理，请稍候。文件较多时可能需要几分钟。")
            self.progress.start(12)
            threading.Thread(target=self.run_worker, daemon=True).start()

        def run_worker(self):
            try:
                if self.mode.get() == "merge":
                    rows = merge_markdown(self.input_path.get())
                    errors = []
                else:
                    rows, errors = extract_all(self.input_path.get())
                output = self.current_output_path()
                if output.exists() and output.is_dir():
                    raise RuntimeError(f"输出路径是文件夹，请填写文件名：\n{output}")
                if not output.parent.exists():
                    raise RuntimeError(f"输出文件夹不存在：\n{output.parent}")
                if output.suffix.lower() == ".json":
                    payload = json.dumps(rows, ensure_ascii=False, indent=2)
                else:
                    payload = to_markdown(rows)
                try:
                    output.write_text(payload, encoding="utf-8")
                except PermissionError as exc:
                    raise RuntimeError(
                        f"没有权限写入：\n{output}\n\n"
                        "请确认文件名不是文件夹，该文件没有在 Word/记事本中打开，"
                        "并且对输出文件夹有写入权限。"
                    ) from exc
                if self.mode.get() == "merge":
                    self.after(0, self.finish_success, len(rows), output, errors)
                    return
                root = Path(self.input_path.get())
                root_name = root.name if root.is_dir() else root.parent.name
                shot_dirs = collect_shot_dirs(root)
                try:
                    zip_paths = pack_output(output, shot_dirs, root_name)
                    first_zip = zip_paths[0] if zip_paths else output
                    msg = f"已生成 {len(zip_paths)} 个压缩包" if len(zip_paths) > 1 else ""
                    self.after(0, self.finish_success, len(rows), first_zip, errors, msg)
                except Exception:
                    self.after(0, self.finish_success, len(rows), output, errors)
            except Exception as exc:
                self.after(0, self.finish_error, str(exc))

        def finish_success(self, count, output, errors, extra_msg=""):
            self.progress.stop()
            self.run_button.configure(state="normal", text="开始汇总")
            self.is_running = False
            extra = f"；{len(errors)} 个文件跳过" if errors else ""
            if extra_msg:
                extra = f"；{extra_msg}{extra}"
            self.status.set(f"完成：{count} 条批注{extra} -> {output}")
            message = f"已生成 {count} 条批注。\n\n{output}"
            if extra_msg:
                message = f"{extra_msg}\n\n{message}"
            if errors:
                message += "\n\n以下文件已跳过：\n" + "\n".join(errors[:8])
                if len(errors) > 8:
                    message += f"\n... 另有 {len(errors) - 8} 个"
            messagebox.showinfo("完成", message)

        def finish_error(self, error):
            self.progress.stop()
            self.run_button.configure(state="normal", text="开始汇总")
            self.is_running = False
            self.status.set("运行失败，请查看弹窗错误。")
            messagebox.showerror("运行失败", error)

        def close_window(self):
            if self.is_running:
                should_close = messagebox.askyesno("确认关闭", "当前仍在处理文件。确定要退出吗？")
                if should_close:
                    os._exit(0)
                return
            self.destroy()

    return App()


if __name__ == "__main__":
    hide_windows_console()
    try:
        append_launch_log(
            "python started\n"
            f"executable={sys.executable}\n"
            f"version={sys.version}\n"
            f"file={__file__}\n"
        )
        app = build_app()
        app.mainloop()
    except Exception as exc:
        show_startup_error(exc)
