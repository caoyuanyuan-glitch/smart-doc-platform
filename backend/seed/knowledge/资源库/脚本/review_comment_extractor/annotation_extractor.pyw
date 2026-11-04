#!pythonw
# -*- coding: utf-8 -*-
"""Self-contained Windows UI for extracting PDF/Word review comments.

Double-click 打开审核意见汇总工具.vbs (preferred) or this .pyw file.
Do not double-click a .py file: Windows will attach a console that looks
like PowerShell and may loop on Microsoft Store python stubs.
"""

from __future__ import annotations

import json
import html as html_lib
import os
import re
import sys
import threading
import traceback
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path


WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
TOOL_VERSION = "v30"
APP_TITLE = f"人工审核意见汇总工具 {TOOL_VERSION}"
EMPTY_SELECTED = "（空——批注覆盖在图上/线框区域，无文本层）"
CARET_MARK = "【^】"
MAX_ZIP_BYTES = 35 * 1024 * 1024


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
CALLOUT_LABEL = re.compile(
    r"^(tips?|notes?|caution|warning|important|notice|attention|注意|提示|警告|小心|注)$",
    re.I,
)
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
INSERT_KW = re.compile(r"插入|insert\b", re.I)
NOTE_TYPE_COMMENT = re.compile(
    r"中文是\s*[「\"'“”]*\s*(注意|提示|警告|小心)"
    r"|note\s*属性|(?:type|note)\s*=\s*(caution|warning|note|tip)",
    re.I,
)
KEEP_SPAN_CHARS = set("&%+#@/=<>×✕·°±µ–—−*")


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
    if text in KEEP_SPAN_CHARS or text in {"x", "X"}:
        return False
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


def is_side_margin(page, annot):
    """页边小标记：矩形贴在版心左右外侧，而不是盖在正文词上。"""
    rect = _as_rect(getattr(annot, "rect", None))
    if rect is None or page is None:
        return False
    page_r = getattr(page, "rect", None)
    if page_r is None:
        return False
    return rect.x1 <= page_r.x0 + 72 or rect.x0 >= page_r.x1 - 72


def looks_like_noise_selected(selected, sentence=""):
    selected = clean(selected)
    if not selected:
        return True
    if sentence:
        for start, end in locate_all_fragments(selected, sentence):
            left_ok = start == 0 or not WORD_CHAR_RE.match(sentence[start - 1])
            right_ok = end >= len(sentence) or not WORD_CHAR_RE.match(sentence[end])
            if left_ok and right_ok:
                return False
    if len(selected) <= 2 and not any(_is_cjk(ch) for ch in selected):
        return True
    collapsed_sentence = (sentence or "").replace(" ", "")
    collapsed_selected = selected.replace(" ", "")
    if collapsed_sentence and collapsed_selected not in collapsed_sentence and len(selected) <= 8:
        return True
    return False


WORD_CHAR_RE = re.compile(r"[A-Za-z0-9\u3400-\u9fff\u3040-\u30ff\uff00-\uffef\-']")

CATEGORY_RULES = [
    ("同步修改/参考其他文件", r"同步修改|参考.{0,8}意见|同中文|另外一份|其他文件"),
    ("交叉引用/页码", r"交叉引用|页码不对|索引条|无法跳转"),
    ("排版/布局/样式", r"列宽|行高|下一页|出框|空隙|边框|对齐|字号|截图|页眉|均匀分布|间隙|加边框|字体不对|topic|换行|居中|图片丢失|重新链接"),
    ("空格/标点/格式", r"空格|逗号|句号|引号|冒号|标点|竖线|乘号|分号|括号"),
    ("拼写错误/错别字/语法", r"错别字|拼写|错字|typo|语法|单复数|冠词"),
    ("重复/冗余/删除", r"删除|删掉|去掉|重复|多余|冗余"),
    ("缺漏/补充内容", r"缺少|漏了|补充|加上|缺了"),
    ("术语统一/用词", r"统一|术语|用词|登陆|登录|存储|储存|中英文不一致|不一致"),
    ("内容确认/疑问", r"确认|是不是|是否|看看|跟.{0,6}确认"),
    ("语言描述优化/润色", r"润色|改写|不通顺|优化描述"),
    ("建议修改/润色", r"建议改|建议为|改为|改成"),
]


def catalog_number(filename):
    name = str(filename or "")
    match = re.search(r"H-\d{3}-\d{6}-\d{2}", name)
    if match:
        return match.group(0)
    match = re.search(r"CSS-\d+", name)
    if match:
        return match.group(0)
    return ""


def guess_category(comment):
    text = clean(comment)
    if not text:
        return "其他"
    for label, pattern in CATEGORY_RULES:
        if re.search(pattern, text, flags=re.I):
            return label
    return "其他"


def _collapsed_indexes(text):
    return [i for i, ch in enumerate(text) if not ch.isspace()]


def locate_fragment(frag, text):
    if not frag or not text:
        return None
    pos = text.find(frag)
    if pos >= 0:
        return pos, pos + len(frag)
    indexes = _collapsed_indexes(text)
    collapsed = "".join(text[i] for i in indexes)
    compact = re.sub(r"\s+", "", frag)
    if not compact:
        return None
    at = collapsed.find(compact)
    if at < 0:
        return None
    start = indexes[at]
    end = indexes[at + len(compact) - 1] + 1
    return start, end


def locate_all_fragments(frag, text):
    """All exact and whitespace-collapsed occurrences of frag in text."""
    hits = []
    seen = set()
    if not frag or not text:
        return hits
    start = 0
    while True:
        pos = text.find(frag, start)
        if pos < 0:
            break
        pair = (pos, pos + len(frag))
        if pair not in seen:
            seen.add(pair)
            hits.append(pair)
        start = pos + 1
    indexes = _collapsed_indexes(text)
    collapsed = "".join(text[i] for i in indexes)
    compact = re.sub(r"\s+", "", frag)
    if not compact:
        return hits
    start = 0
    while True:
        at = collapsed.find(compact, start)
        if at < 0:
            break
        pair = (indexes[at], indexes[at + len(compact) - 1] + 1)
        if pair not in seen:
            seen.add(pair)
            hits.append(pair)
        start = at + 1
    return hits


def _anchor_score(hay, start, end, left, right):
    score = 0
    def norm(text):
        return re.sub(r"\s+", " ", text or "").strip()

    nleft = norm(left)
    nright = norm(right)
    if nleft:
        before = norm(hay[:start])
        if before.endswith(nleft):
            score += 4
        elif before.split()[-1:] == nleft.split()[-1:]:
            score += 2
    if nright:
        after = norm(hay[end:])
        if after.startswith(nright):
            score += 4
        elif after.split()[:1] == nright.split()[:1]:
            score += 2
    return score


def expand_span(text, start, end, max_chars=24):
    cjk = any(_is_cjk(ch) for ch in text[start:end])

    def can_take(ch):
        if not ch or not WORD_CHAR_RE.match(ch):
            return False
        if cjk and ch in CJK_BREAK_CHARS:
            return False
        return True

    while start > 0 and can_take(text[start - 1]) and (end - start) < max_chars:
        start -= 1
    while end < len(text) and can_take(text[end]) and (end - start) < max_chars:
        end += 1
    return start, end


def expand_selected(selected, sentence):
    """把框选碎片还原成完整词/短语，例如 部储存设 → 外部储存设备。"""
    selected = clean(selected)
    block = clean_block(sentence or "")
    if not selected:
        return ""
    if not block:
        return selected
    candidates = []
    seen = set()
    variants = list(block.splitlines())
    variants.append(re.sub(r"\s+", " ", block))
    variants.append(re.sub(r"-\s+", "-", block))
    variants.append(re.sub(r"-\s+", "-", re.sub(r"\s+", " ", block)))
    for line in variants:
        loc = locate_fragment(selected, line)
        if not loc:
            continue
        limit = 24 if any(_is_cjk(ch) for ch in selected) else 48
        start, end = expand_span(line, loc[0], loc[1], max_chars=limit)
        piece = line[start:end].strip()
        if piece and piece not in seen:
            seen.add(piece)
            candidates.append(piece)
    if not candidates:
        return selected
    def rank(piece):
        extra_words = max(0, piece.count(" ") - selected.count(" "))
        hyphen_bonus = 1 if ("-" in piece and "-" not in selected) else 0
        return (extra_words, -hyphen_bonus, -len(piece), piece)
    candidates.sort(key=rank)
    return candidates[0]


def clip_text(text, limit=60):
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "..."


def md_cell(text):
    return clip_text(text, 80).replace("|", "/")


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


def _symbol_needles(selected):
    """Variants so 5× / 5x / 5 能对上文本层。"""
    text = selected or ""
    out = []
    seen = set()

    def add(item):
        item = clean(item)
        if item and item not in seen:
            seen.add(item)
            out.append(item)

    add(text)
    folded = (
        text.replace("×", "x")
        .replace("✕", "x")
        .replace("−", "-")
        .replace("–", "-")
        .replace("—", "-")
        .replace("’", "'")
        .replace("‘", "'")
    )
    add(folded)
    add(re.sub(r"[×✕]", "", text))
    add(re.sub(r"[×✕]", " ", text))
    return out


def mark_snippet(text, selected, prefer="", left="", right=""):
    block = clean_block(text)
    selected = clean(selected)
    if CARET_MARK in block:
        if f"**{CARET_MARK}**" in block:
            return block
        return block.replace(CARET_MARK, f"**{CARET_MARK}**", 1)
    prefer = clean_block(prefer or "")
    left = left or ""
    right = right or ""

    def mark_at(hay, start, end):
        return hay[:start] + f"**【{hay[start:end]}】**" + hay[end:]

    def mark_in(hay, needle, require_anchor=False):
        if not hay or not needle:
            return None
        hits = []
        for cand in _symbol_needles(needle):
            hits = locate_all_fragments(cand, hay)
            if hits:
                break
        if not hits:
            return None
        if left or right:
            best = max(hits, key=lambda loc: _anchor_score(hay, loc[0], loc[1], left, right))
            if _anchor_score(hay, best[0], best[1], left, right) > 0:
                return mark_at(hay, best[0], best[1])
            if require_anchor:
                return None
        start, end = hits[0]
        return mark_at(hay, start, end)

    if prefer and prefer in block and selected:
        marked_pref = mark_in(prefer, selected, require_anchor=bool(left or right))
        if marked_pref:
            return block.replace(prefer, marked_pref, 1)
    marked = mark_in(block, selected)
    if marked:
        return marked
    first = clean_block(selected).splitlines()[0] if selected else ""
    return mark_in(block, first) or block


def location_span(row):
    """用于在原文里标记问题位置：只标框选还原，空框选不强行标整句或图注数字。"""
    return clean(row.get("selected") or "")


def useful_selected(selected, sentence, marker):
    selected = clean(selected)
    if not selected:
        return ""
    if looks_like_noise_selected(selected, sentence):
        return ""
    return selected


def markup_rects(annot, pad=1.5):
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
    if pad:
        return [rect + (-pad, -pad, pad, pad) for rect in rects]
    return rects


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


def glyph_hits_rects(box, rects):
    """字心落在框内才算框选，避免空框擦到旁边的词。"""
    box = _as_rect(box)
    if box is None or box.is_empty or box.is_infinite:
        return False
    cx = (box.x0 + box.x1) / 2.0
    cy = (box.y0 + box.y1) / 2.0
    for rect in rects:
        rect = _as_rect(rect)
        if rect is None or rect.is_empty or rect.is_infinite:
            continue
        if rect.x0 <= cx <= rect.x1 and rect.y0 <= cy <= rect.y1:
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


def boxed_char_lines(page, rects, strict=False):
    payload = page.get_text("rawdict")
    hit_fn = glyph_hits_rects if strict else box_hits_rects
    lines = []
    for block in payload.get("blocks", []):
        if block.get("type", 0) != 0:
            continue
        for line in block.get("lines", []):
            full = []
            hit = []
            boxes = []
            for span in line.get("spans", []):
                chars = span.get("chars")
                if not chars:
                    text = span.get("text") or ""
                    bbox = _as_rect(span.get("bbox"))
                    full.append(text)
                    if text and bbox is not None and hit_fn(bbox, rects):
                        hit.append(text)
                        boxes.append(bbox)
                    continue
                for char in chars:
                    glyph = char.get("c") or ""
                    box = _as_rect(char.get("bbox"))
                    if not glyph or box is None:
                        continue
                    full.append(glyph)
                    if hit_fn(box, rects):
                        hit.append(glyph)
                        boxes.append(box)
            if not hit or not boxes:
                continue
            full_text = "".join(full)
            hit_text = "".join(hit)
            loc = locate_fragment(hit_text, full_text)
            lines.append({
                "y0": min(box.y0 for box in boxes),
                "hit": hit_text,
                "full": full_text,
                "left": full_text[:loc[0]] if loc else "",
                "right": full_text[loc[1]:] if loc else "",
                "at_eol": bool(full_text.rstrip().endswith(hit_text.rstrip())),
                "at_sol": bool(full_text.lstrip().startswith(hit_text.lstrip())),
            })
    lines.sort(key=lambda item: item["y0"])
    return lines


def selected_from_chars(page, rects):
    return join_wrapped_hits(boxed_char_lines(page, rects))


def boxed_anchors_from_lines(lines, window=16):
    if not lines:
        return "", ""
    left = (lines[0].get("left") or "")[-window:]
    right = (lines[0].get("right") or "")[:window]
    return left, right


def _first_token(text):
    match = re.match(r"^[A-Za-z0-9._\-/\\']+", text or "")
    return match.group(0) if match else (text.split() or [""])[0]


def is_token_wrap(prev, nxt):
    if not prev or not nxt:
        return False
    a, b = prev[-1], nxt[0]
    if a == "-":
        return True
    if _is_cjk(a) or _is_cjk(b):
        return True
    if a == "/":
        tok = _first_token(nxt)
        return bool(tok) and ("/" in tok or "." in tok)
    return bool(WORD_CHAR_RE.match(a) and WORD_CHAR_RE.match(b))


def merge_wrap_token(prev, extra):
    if not extra:
        return prev
    if prev.endswith("-") or prev.endswith("/") or _is_cjk(prev[-1]) or _is_cjk(extra[0]):
        return prev + extra
    if WORD_CHAR_RE.match(prev[-1]) and WORD_CHAR_RE.match(extra[0]):
        return prev + " " + extra
    return prev + extra


def join_wrapped_hits(lines):
    """跨行高亮：只补被截断的词/路径，不把下一行的新词拼进来。"""
    if not lines:
        return ""
    result = (lines[0].get("hit") or "").rstrip()
    for i in range(1, len(lines)):
        nxt = (lines[i].get("hit") or "").lstrip()
        if not nxt:
            continue
        prev_info = lines[i - 1]
        wrap = bool(prev_info.get("at_eol") and lines[i].get("at_sol"))
        if wrap:
            full = (lines[i].get("full") or "").strip()
            nxt_full_line = bool(full) and nxt.strip() == full
            if nxt_full_line:
                result = merge_wrap_token(result, nxt) if is_token_wrap(result, nxt) else join_fragments([result, nxt])
            elif is_token_wrap(result, nxt):
                extra = _first_token(nxt)
                result = merge_wrap_token(result, extra)
                if nxt[len(extra):].strip():
                    break
            else:
                break
        else:
            result = join_fragments([result, nxt])
    return strip_bullet_junk(clean(result))


def is_heading_span(span, body_size):
    text = clean(span["text"])
    if body_size and span["size"] >= body_size * 1.15 + 0.4:
        return True
    return bool(HEADING_LINE.match(text) and len(text) <= 40)


def is_callout_label(text):
    return bool(CALLOUT_LABEL.match(clean(text).rstrip(":：")))


def callout_label_in_text(*parts):
    for part in parts:
        for line in clean_block(part or "").splitlines():
            if is_callout_label(line):
                return clean(line).rstrip(":：")
    return ""


def nearest_callout_label(spans, hit_ids):
    if not spans:
        return ""
    anchors = hit_ids or list(range(len(spans)))
    best = None
    for i, span in enumerate(spans):
        if not is_callout_label(span.get("text")):
            continue
        dist = min(abs(i - h) for h in anchors)
        if best is None or dist < best[0]:
            best = (dist, clean(span["text"]).rstrip(":："))
    if best and best[0] <= 8:
        return best[1]
    return ""


def union_boxes(boxes):
    import fitz

    clip = None
    for box in boxes:
        box = _as_rect(box)
        if box is None or box.is_empty or box.is_infinite:
            continue
        clip = box if clip is None else (fitz.Rect(clip) | box)
    return clip


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
            dx = rect.x0 - box.x1
        elif box.x0 > rect.x1 + 8:
            dx = box.x0 - rect.x1
        else:
            dx = 0
        length_bonus = min(len(clean(span["text"])), 24) * 0.15
        label_bonus = 22 if is_callout_label(span["text"]) else 0
        cover_bonus = 8 if box_hits_rects(box, [rect]) else 0
        scored.append((dx, dy + dx * 1.6 - length_bonus - label_bonus - cover_bonus, i))
    if not scored:
        return nearest_span_ids(spans, rect, max_dist=max_dist)
    in_col = [item for item in scored if item[0] <= 18]
    use = in_col or scored
    use.sort(key=lambda item: item[1])
    best = use[0][1]
    hits = [i for _dx, dist, i in use if dist <= best + 4]
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


def _needs_neighbor_context(sentence):
    text = clean(sentence)
    if not text:
        return True
    compact = re.sub(r"\s+", "", text)
    if len(compact) <= 12:
        return True
    if text.endswith(("（", "(", "（选", "(选")):
        return True
    return False


def context_view(spans, hit_ids):
    if not spans or not hit_ids:
        return "", "", "", None
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
    callout_in_range = any(
        is_callout_label(line_text_from_ids(spans, groups[k]))
        for k in range(lo, hi + 1)
    ) or is_callout_label(sentence)
    if callout_in_range:
        while hi < len(groups) - 1:
            nxt_text = line_text_from_ids(spans, groups[hi + 1])
            if is_callout_label(nxt_text) and hi >= gindex:
                break
            if HEADING_LINE.match(nxt_text or ""):
                break
            if gap_groups(hi, hi + 1) > line_h * 2.6:
                break
            hi += 1
            if bundled_len(lo, hi) >= 900:
                break
        probe = lo
        while probe > 0:
            if gap_groups(probe - 1, probe) > max(line_h * 6, 90):
                break
            prev_text = line_text_from_ids(spans, groups[probe - 1])
            prev_span = spans[groups[probe - 1][0]]
            lo = probe - 1
            if is_heading_span(prev_span, body_size) or HEADING_LINE.match(prev_text or ""):
                heading_idx = lo
                break
            probe -= 1
            if gindex - lo > 10:
                break
        lines = [line_text_from_ids(spans, groups[k]) for k in range(lo, hi + 1)]
        lines = [line for line in lines if line]
        heading = line_text_from_ids(spans, groups[heading_idx]) if heading_idx is not None else heading
    if _needs_neighbor_context(sentence):
        hit_block = spans[groups[gindex][0]]["block"]
        while lo > 0 and spans[groups[lo - 1][0]]["block"] == hit_block:
            lo -= 1
        while hi < len(groups) - 1 and spans[groups[hi + 1][0]]["block"] == hit_block:
            hi += 1
        y0 = spans[groups[gindex][0]]["y0"]
        y1 = spans[groups[gindex][-1]]["y1"]
        while lo > 0 and gindex - lo < 3:
            prev_y1 = spans[groups[lo - 1][-1]]["y1"]
            if y0 - prev_y1 > 48:
                break
            lo -= 1
        while hi < len(groups) - 1 and hi - gindex < 3:
            nxt_y0 = spans[groups[hi + 1][0]]["y0"]
            if nxt_y0 - y1 > 48:
                break
            hi += 1
        lines = [line_text_from_ids(spans, groups[k]) for k in range(lo, hi + 1)]
        lines = [line for line in lines if line]
        if heading_idx is not None:
            heading = line_text_from_ids(spans, groups[heading_idx])
    boxes = [spans[i]["bbox"] for k in range(lo, hi + 1) for i in groups[k]]
    return heading, sentence, "\n".join(lines), union_boxes(boxes)


def extract_caret_anchor(page, annot):
    """定位 Caret 插入点：返回插入点前后各一个词，以及是否在行首。"""
    rect = _as_rect(getattr(annot, "rect", None))
    if rect is None:
        return None
    # Caret 图标画在插入点右侧，插入横坐标取 annot 左缘，避免把首字母切到标记左边。
    cx = rect.x0
    cy = (rect.y0 + rect.y1) / 2
    payload = page.get_text("rawdict")
    rows = []
    for block in payload.get("blocks", []):
        if block.get("type", 0) != 0:
            continue
        for line in block.get("lines", []):
            chars = []
            for span in line.get("spans", []):
                for char in span.get("chars") or []:
                    glyph = char.get("c") or ""
                    box = _as_rect(char.get("bbox"))
                    if glyph and box is not None:
                        chars.append({
                            "x0": box.x0,
                            "x1": box.x1,
                            "y0": box.y0,
                            "y1": box.y1,
                            "glyph": glyph,
                        })
            if not chars:
                continue
            ymid = sum((item["y0"] + item["y1"]) / 2 for item in chars) / len(chars)
            rows.append({
                "y": ymid,
                "chars": chars,
                "text": "".join(item["glyph"] for item in chars),
            })
    if not rows:
        return None

    def x_range(row):
        return min(c["x0"] for c in row["chars"]), max(c["x1"] for c in row["chars"])

    def row_score(row):
        x0, x1 = x_range(row)
        dy = abs(row["y"] - cy)
        if x0 - 8 <= cx <= x1 + 8:
            dx = 0
        elif cx < x0:
            dx = x0 - cx
        else:
            dx = cx - x1
        return (dx * dx * 6 + dy * dy, dx, dy)

    containing = [row for row in rows if x_range(row)[0] - 14 <= cx <= x_range(row)[1] + 14]
    chosen = min(containing or rows, key=row_score)
    before, after = [], []
    for item in chosen["chars"]:
        if item["x0"] < cx - 0.4:
            before.append(item["glyph"])
        else:
            after.append(item["glyph"])
    left = "".join(before)
    right = "".join(after)
    left_tok = (re.findall(r"\S+", left) or [""])[-1]
    right_tok = (re.findall(r"\S+", right) or [""])[0]
    selected = f"{left_tok}{CARET_MARK}{right_tok}".strip()
    if selected == CARET_MARK:
        selected = CARET_MARK
    import fitz

    x0, x1 = x_range(chosen)
    same_col = []
    for row in rows:
        rx0, rx1 = x_range(row)
        overlap = min(x1, rx1) - max(x0, rx0)
        width = max(min(x1 - x0, rx1 - rx0), 1.0)
        if overlap >= 0.25 * width or abs(((rx0 + rx1) / 2) - ((x0 + x1) / 2)) <= 36:
            same_col.append(row)
    near = []
    for row in same_col:
        if abs(row["y"] - chosen["y"]) > 52:
            continue
        text = (row["text"] or "").strip()
        if row is not chosen and HEADING_LINE.match(text):
            continue
        near.append(row)
    near.sort(key=lambda row: abs(row["y"] - chosen["y"]))
    near = sorted(near[:8], key=lambda row: row["y"])
    clip = fitz.Rect(
        min(c["x0"] for c in chosen["chars"]),
        min(c["y0"] for c in chosen["chars"]),
        max(c["x1"] for c in chosen["chars"]),
        max(c["y1"] for c in chosen["chars"]),
    )
    for row in near:
        for item in row["chars"]:
            clip |= fitz.Rect(item["x0"], item["y0"], item["x1"], item["y1"])
    return {
        "left": left,
        "right": right,
        "selected": selected or CARET_MARK,
        "at_sol": not bool(left.strip()),
        "sentence": chosen["text"],
        "context": "\n".join(row["text"] for row in near) or chosen["text"],
        "clip": clip,
    }


def inject_caret_mark(context, sentence, caret):
    """把 【^】 插入命中行，保留整段上下文。"""
    left = caret.get("left") or ""
    right = caret.get("right") or ""
    raw_line = f"{left}{right}".strip()
    marked_fallback = f"{left.rstrip()}{CARET_MARK}{right.lstrip()}" or CARET_MARK

    def mark_line(line):
        if caret.get("at_sol"):
            if line.startswith(CARET_MARK):
                return line
            return CARET_MARK + line
        right_bit = right.lstrip()
        if right_bit and right_bit in line:
            at = line.find(right_bit)
            return line[:at] + CARET_MARK + line[at:]
        left_bit = left.rstrip()
        if left_bit and left_bit in line:
            at = line.find(left_bit) + len(left_bit)
            return line[:at] + CARET_MARK + line[at:]
        if line.endswith(CARET_MARK):
            return line
        return f"{line.rstrip()}{CARET_MARK}"

    lines = (context or "").splitlines()
    right_bit = right.lstrip()
    left_bit = left.rstrip()
    best_i = None
    best_score = -1
    for i, line in enumerate(lines):
        stripped = line.strip()
        score = 0
        if raw_line and (raw_line in line or stripped == raw_line):
            score += 10
        if right_bit and right_bit in line:
            score += 4
        if left_bit and left_bit in line:
            score += 3
        if score > best_score:
            best_score = score
            best_i = i
    if best_i is not None and best_score >= 4:
        lines[best_i] = mark_line(lines[best_i])
        return "\n".join(lines), lines[best_i]
    if sentence and raw_line and (raw_line in sentence or sentence in raw_line):
        marked = mark_line(sentence)
    else:
        marked = marked_fallback
    if sentence and context and sentence in context:
        return context.replace(sentence, marked, 1), marked
    if marked in (context or ""):
        return context, marked
    return ((context + "\n") if context else "") + marked, marked


def extract_comment_view(page, annot):
    try:
        rects = markup_rects(annot)
        typ = annot.type[1] if annot.type else ""
        comment = clean((annot.info or {}).get("content"))
        spans = collect_spans(page)
        marker = is_margin_marker(annot)
        hit_ids = [i for i, span in enumerate(spans) if box_hits_rects(span["bbox"], rects)]
        if not hit_ids:
            pointed = pointed_span_ids(spans, annot.rect)
            if pointed:
                hit_ids = pointed

        strict_box = typ not in MARKUP_TYPES and typ != "Caret"
        char_lines = boxed_char_lines(
            page,
            markup_rects(annot, pad=0 if strict_box else 1.5),
            strict=strict_box,
        )
        glyph_selected = join_wrapped_hits(char_lines)
        selected = glyph_selected
        anchor_left, anchor_right = boxed_anchors_from_lines(char_lines)
        if not selected and not marker:
            if hit_ids:
                selected = join_fragments(
                    [spans[i]["text"] for i in hit_ids if not is_junk_span(spans[i])]
                )
            if not selected:
                selected = strip_bullet_junk(clean(page.get_textbox(annot.rect)))

        heading, sentence, context, clip = context_view(spans, hit_ids)
        if char_lines and not (context or sentence):
            sentence = clean(char_lines[0].get("full") or "")
            context = clean_block("\n".join(line.get("full") or "" for line in char_lines))
        if not context:
            context = sentence or selected
        if is_callout_label(sentence):
            selected = sentence
        caret = extract_caret_anchor(page, annot) if typ == "Caret" else None
        if caret:
            selected = caret["selected"]
            if caret.get("sentence"):
                sentence = caret["sentence"]
            if caret.get("context"):
                context = caret["context"]
            context, sentence = inject_caret_mark(context, sentence, caret)
            if caret.get("clip") is not None:
                clip = caret["clip"]
        else:
            selected = expand_selected(selected, sentence or context)
            if typ not in MARKUP_TYPES and not glyph_selected:
                selected = useful_selected(selected, sentence or context, marker)
            label = callout_label_in_text(heading, sentence, context)
            label = label or nearest_callout_label(spans, hit_ids)
            if label and NOTE_TYPE_COMMENT.search(comment):
                selected = label
                if label not in (context or ""):
                    context = label + "\n" + (context or "")
        return {
            "selected": selected,
            "heading": heading,
            "sentence": sentence,
            "context": context,
            "change": interpret_change(selected, comment, sentence or context),
            "clip": clip,
            "anchor_left": anchor_left,
            "anchor_right": anchor_right,
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
            "clip": None,
            "anchor_left": "",
            "anchor_right": "",
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


def save_annot_shot(page, annot, out_dir, idx, prefix, clip=None):
    """渲染批注区域及上下文为 JPEG。只保留 PDF 原注释，不另画矩形。"""
    try:
        import fitz

        out_dir.mkdir(parents=True, exist_ok=True)
        page_r = page.rect
        boxes = [annot.rect]
        text_clip = _as_rect(clip)
        if text_clip is not None:
            boxes.append(text_clip)
        shot_clip = union_boxes(boxes) or annot.rect
        pad_x, pad_y = 40, 100
        shot_clip = fitz.Rect(
            max(page_r.x0 + 6, shot_clip.x0 - pad_x),
            max(page_r.y0 + 6, shot_clip.y0 - pad_y),
            min(page_r.x1 - 6, shot_clip.x1 + pad_x),
            min(page_r.y1 - 6, shot_clip.y1 + pad_y),
        )
        if shot_clip.height < 360:
            extra = (360 - shot_clip.height) / 2
            shot_clip = fitz.Rect(
                shot_clip.x0,
                max(page_r.y0 + 6, shot_clip.y0 - extra),
                shot_clip.x1,
                min(page_r.y1 - 6, shot_clip.y1 + extra),
            )
        if shot_clip.width < 380:
            extra = (380 - shot_clip.width) / 2
            shot_clip = fitz.Rect(
                max(page_r.x0 + 6, shot_clip.x0 - extra),
                shot_clip.y0,
                min(page_r.x1 - 6, shot_clip.x1 + extra),
                shot_clip.y1,
            )
        scale = max(1.0, min(1.6, 1100 / max(shot_clip.width, 1)))
        pix = page.get_pixmap(
            matrix=fitz.Matrix(scale, scale),
            clip=shot_clip,
            colorspace=fitz.csRGB,
            annots=True,
        )
        name = f"{prefix}_p{page.number + 1}_ann{idx}.jpg"
        if max(pix.width, pix.height) > 1600:
            shrink = 1600 / max(pix.width, pix.height)
            scale = scale * shrink
            pix = page.get_pixmap(
                matrix=fitz.Matrix(scale, scale),
                clip=shot_clip,
                colorspace=fitz.csRGB,
                annots=True,
            )
        pix.save(str(out_dir / name), jpg_quality=55)
        return name
    except Exception:
        return ""


def is_thin_context(selected, context, sentence=""):
    """定位原文过短或几乎只剩框选碎片时，读者看不懂，需要截图。"""
    sel = clean(selected)
    ctx = clean_block(context or sentence or "")
    if not ctx:
        return False
    compact_ctx = re.sub(r"\s+", "", ctx)
    compact_sel = re.sub(r"\s+", "", sel)
    if len(compact_ctx) <= 12:
        return True
    if compact_sel:
        remainder = compact_ctx.replace(compact_sel, "", 1)
        if len(remainder) < 8:
            return True
    if sel.endswith(("（", "(", "（选", "(选")):
        return True
    return False


def is_visual_annot(page, annot, selected, comment, context=""):
    """意见双向判定：视觉词→图；空框选/对不上原文→图；文本词→免图。"""
    c = comment or ""
    typ = ""
    try:
        if annot is not None and getattr(annot, "type", None):
            typ = annot.type[1]
    except Exception:
        pass
    if not clean(selected):
        return True
    if is_insertion(typ, selected, c):
        return True
    if is_callout_label(selected):
        return True
    if VISUAL_KW.search(c):
        return True
    if context and selected and not locate_fragment(selected, context):
        return True
    if is_thin_context(selected, context):
        return True
    if TEXTUAL_KW.search(c):
        return False
    return False


def needs_screenshot(page, annot, selected, comment, context=""):
    """空框选必须出图；其余走视觉判定。"""
    if not clean(selected):
        return True
    return is_visual_annot(page, annot, selected, comment, context)


def is_insertion(typ, selected, comment):
    if typ == "Caret":
        return True
    if CARET_MARK in (selected or ""):
        return True
    return bool(INSERT_KW.search(comment or ""))


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


def summary_export_files(md_path):
    """只收同名 md/html，忽略 json、jsonl 和其它附属文件。"""
    md_path = Path(md_path)
    files = []
    seen = set()
    for path in (md_path, md_path.with_suffix(".md"), md_path.with_suffix(".html")):
        if not path.is_file() or path.suffix.lower() not in {".md", ".html"}:
            continue
        key = path.resolve()
        if key in seen:
            continue
        seen.add(key)
        files.append(path)
    return files


def clear_previous_packs(md_path):
    """清掉同名上次生成的 zip，避免旧分卷残留成几百个包。"""
    md_path = Path(md_path)
    parent = md_path.parent
    stem = md_path.stem
    leftovers = [parent / f"{stem}.zip"]
    leftovers.extend(sorted(parent.glob(f"{stem}.part*.zip")))
    for path in leftovers:
        if path.is_file():
            try:
                path.unlink()
            except OSError:
                pass


def split_shot_batches(shots, doc_size, max_bytes):
    """按截图体积分卷：每卷尽量装满上限；单张图超过上限时单独成卷。"""
    shot_budget = max_bytes - doc_size
    if shot_budget <= 0:
        shot_budget = max_bytes
    batches, cur, cur_size = [], [], 0
    for shot in shots:
        size = shot.stat().st_size
        if cur and cur_size + size > shot_budget:
            batches.append(cur)
            cur, cur_size = [], 0
        cur.append(shot)
        cur_size += size
    if cur or not batches:
        batches.append(cur)
    return batches


def pack_output(md_path, shot_dirs, root_name, max_bytes=MAX_ZIP_BYTES):
    """打包人工审核意见 md/html + 截图。json/jsonl 等其它文件不进包。
    总体不超过约 35MB 打成一个 zip；超过才按 35MB 装满后拆卷，每卷带完整 md/html。"""
    md_path = Path(md_path)
    top = root_name or "批注截图汇总"
    docs = summary_export_files(md_path)
    if not docs:
        raise RuntimeError(f"没有可打包的 md/html：{md_path}")

    shots = []
    for shot_dir in shot_dirs or []:
        shot_dir = Path(shot_dir)
        if shot_dir.exists():
            for shot in sorted(shot_dir.rglob("*.jpg")):
                if shot.is_file():
                    shots.append(shot)

    doc_size = sum(path.stat().st_size for path in docs)
    batches = split_shot_batches(shots, doc_size, max_bytes)
    clear_previous_packs(md_path)

    zip_paths = []
    for i, batch in enumerate(batches, 1):
        if len(batches) == 1:
            zip_path = md_path.with_suffix(".zip")
        else:
            zip_path = md_path.with_suffix(f".part{i}.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for doc in docs:
                zf.write(doc, f"{top}/{doc.name}")
            for shot in batch:
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
                    empty_box = not clean(view["selected"])
                    filename = ""
                    if empty_box or needs_screenshot(
                        page, annot, view["selected"], comment, view.get("context") or view.get("sentence")
                    ):
                        filename = save_annot_shot(
                            page, annot, shot_dir, idx, prefix, clip=view.get("clip")
                        )
                        if not filename:
                            filename = save_annot_shot(page, annot, shot_dir, idx, prefix, clip=None)
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
                        "doc_no": catalog_number(Path(pdf).name),
                        "category": guess_category(comment),
                        "anchor_left": view.get("anchor_left") or "",
                        "anchor_right": view.get("anchor_right") or "",
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
            selected = expand_selected(selected, selected)
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
                "doc_no": catalog_number(Path(docx).name),
                "category": guess_category(comment),
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
            "selected": parse_section(block, "框选还原") or parse_section(block, "批注覆盖文本") or parse_bullet(block, "选中文本"),
            "context": parse_section(block, "定位原文") or parse_section(block, "原文") or parse_bullet(block, "附近正文"),
            "heading": "",
            "sentence": "",
            "change": parse_section(block, "改什么"),
            "rect": parse_bullet(block, "批注矩形"),
            "shot": parse_bullet(block, "批注截图"),
            "doc_no": parse_bullet(block, "文档号") or catalog_number(header.group(1)),
            "category": parse_bullet(block, "建议分类") or guess_category(parse_section(block, "人工意见") or parse_bullet(block, "人工意见")),
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
    body = context or sentence
    marked = mark_snippet(
        body,
        location_span(row),
        prefer=sentence,
        left=row.get("anchor_left") or "",
        right=row.get("anchor_right") or "",
    )
    span = location_span(row)
    if span and CARET_MARK not in marked and "**【" not in marked:
        loc = locate_fragment(span, marked)
        if loc:
            marked = marked[:loc[0]] + f"**【{marked[loc[0]:loc[1]]}】**" + marked[loc[1]:]
        else:
            marked = f"**【{span}】**" + (("\n" + marked) if marked else "")
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
    lines = [
        "# 人工审核 PDF 和 Word 批注汇总",
        "",
        "> 给后续整理/AI 分类用。每条含文档号、页码、定位原文（【】标出问题位置）、框选还原、人工意见。",
        "> 请按「人工意见」语义分类；框选还原只表示位置。建议分类仅供参考。",
        "",
        f"总条数：**{len(rows)}**",
        "",
        "## 分类统计",
        "",
        "| 建议分类 | 条数 |",
        "|---|---|",
    ]
    counts = {}
    for row in rows:
        cat = row.get("category") or guess_category(row.get("comment"))
        counts[cat] = counts.get(cat, 0) + 1
    for cat, n in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"| {md_cell(cat)} | {n} |")
    lines += [
        "",
        "## 分类索引",
        "",
        "| 序号 | 文档号 | 页码 | 建议分类 | 定位原文 | 人工意见 |",
        "|---|---|---|---|---|---|",
    ]
    for i, row in enumerate(rows, start=1):
        lines.append(
            "| {i} | {doc} | {page} | {cat} | {orig} | {cmt} |".format(
                i=i,
                doc=md_cell(row.get("doc_no") or catalog_number(row.get("file")) or "-"),
                page=md_cell(row.get("page")),
                cat=md_cell(row.get("category") or guess_category(row.get("comment"))),
                orig=md_cell(clip_text(format_original(row), 60)),
                cmt=md_cell(clip_text(row.get("comment"), 40)),
            )
        )
    lines += ["", "---", ""]
    for i, row in enumerate(rows, start=1):
        comment = row.get("comment") or "-"
        lines += [
            f"## {i}. {row['file']} · 第 {row['page']} 页",
            "",
            f"- 文档号: {row.get('doc_no') or catalog_number(row.get('file')) or '-'}",
            f"- 建议分类: {row.get('category') or guess_category(comment)}",
            f"- 批注人: {row['author'] or '-'}",
            f"- 批注类型: {row['type']}",
            f"- 批注截图: {row.get('shot') or '-'}",
            "",
            "### 框选还原",
            format_selected_text(row),
            "",
            "### 定位原文",
            format_original(row),
            "",
        ]
        shot = (row.get("shot") or "").strip()
        if shot and shot != "-":
            lines += [
                f"![批注截图]({shot})",
                "",
            ]
        lines += [
            "### 人工意见",
            comment,
            "",
        ]
    return "\n".join(lines)


def resolve_shot_file(shot, search_dirs=None):
    shot = (shot or "").strip().replace("\\", "/")
    if not shot or shot == "-":
        return None
    path = Path(shot)
    if path.is_file():
        return path
    name = path.name
    for folder in search_dirs or []:
        if not folder:
            continue
        folder = Path(folder)
        for candidate in (folder / shot, folder / name, folder / "批注截图" / name):
            if candidate.is_file():
                return candidate
    return None


def html_shot_src(shot, search_dirs=None):
    """HTML 用相对路径引用截图，避免内嵌图片把 html/zip 撑爆。"""
    raw = str(shot or "").replace("\\", "/")
    path = resolve_shot_file(shot, search_dirs)
    name = path.name if path is not None else Path(raw).name
    if name:
        return f"批注截图/{name}"
    return raw


def to_html(rows, search_dirs=None):
    """输出 HTML 版汇总，框选文本用高亮，截图用相对路径。"""
    def esc(text):
        return html_lib.escape(str(text or ""))

    parts = [
        "<!DOCTYPE html>",
        '<html lang="zh-CN"><head><meta charset="utf-8">',
        "<title>人工审核批注汇总</title>",
        "<style>",
        'body{font-family:"Microsoft YaHei",sans-serif;max-width:900px;margin:20px auto;padding:0 20px;line-height:1.7}',
        ".card{border:1px solid #ddd;border-radius:8px;padding:16px;margin:16px 0;background:#fafafa}",
        ".meta{color:#666;font-size:13px;margin-bottom:8px}",
        ".tag{display:inline-block;background:#e3f2fd;padding:2px 8px;border-radius:4px;font-size:12px;margin-right:8px}",
        ".orig{background:#fff;padding:12px;border-left:4px solid #2196F3;margin:8px 0;white-space:pre-wrap}",
        ".issue{background:#fff3e0;padding:12px;border-left:4px solid #ff9800;margin:8px 0}",
        "mark{background:#ffeb3b;color:#d32f2f;padding:1px 4px;border-radius:2px;font-weight:bold}",
        "img{max-width:100%;border:1px solid #ddd;margin:8px 0}",
        "h1{color:#333}h2{color:#1976D2;font-size:18px;margin-top:0}",
        "table{border-collapse:collapse;width:100%;font-size:13px;margin:12px 0}",
        "th,td{border:1px solid #ddd;padding:6px 8px;text-align:left;vertical-align:top}",
        "th{background:#e3f2fd}",
        "</style></head><body>",
        "<h1>人工审核批注汇总</h1>",
    ]
    parts.append(f"<p>总条数：<b>{len(rows)}</b>。定位原文里的高亮是问题位置；请按人工意见分类。</p>")
    counts = {}
    for row in rows:
        cat = row.get("category") or guess_category(row.get("comment"))
        counts[cat] = counts.get(cat, 0) + 1
    parts.append("<h2>分类统计</h2><table><tr><th>建议分类</th><th>条数</th></tr>")
    for cat, n in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        parts.append(f"<tr><td>{esc(cat)}</td><td>{n}</td></tr>")
    parts.append("</table>")
    for i, row in enumerate(rows, 1):
        original = format_original(row)
        orig_html = esc(original)
        orig_html = re.sub(r"\*\*【(.*?)】\*\*", r"<mark>【\1】</mark>", orig_html, flags=re.S)
        shot = (row.get("shot") or "").strip()
        doc_no = row.get("doc_no") or catalog_number(row.get("file")) or "-"
        category = row.get("category") or guess_category(row.get("comment"))
        parts.append('<div class="card">')
        parts.append(f"<h2>#{i} · {esc(row.get('file'))} · 第 {esc(row.get('page'))} 页</h2>")
        parts.append(
            f'<div class="meta"><span class="tag">{esc(category)}</span>'
            f'<span class="tag">{esc(row.get("type"))}</span> 文档号: {esc(doc_no)}　建议分类: {esc(category)}　批注人: {esc(row.get("author"))}</div>'
        )
        parts.append(f'<div class="meta">框选还原: <b>{esc(format_selected_text(row))}</b></div>')
        parts.append(f'<div class="orig">{orig_html}</div>')
        if shot and shot != "-":
            shot_name = Path(shot).name
            caption = "插入点截图" if is_insertion(row.get("type"), row.get("selected"), row.get("comment")) else "批注截图"
            parts.append(f'<p class="meta">{esc(caption)}</p>')
            parts.append(f'<img src="{esc(html_shot_src(shot, search_dirs))}" alt="{esc(caption)}">')
        parts.append(f'<div class="issue"><b>人工意见:</b> {esc(row.get("comment"))}</div>')
        parts.append("</div>")
    parts.append("</body></html>")
    return "\n".join(parts)


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
                    if output.suffix.lower() != ".json":
                        root = Path(self.input_path.get())
                        if root.is_file():
                            root = root.parent
                        search_dirs = [output.parent, root]
                        search_dirs.extend(collect_shot_dirs(root))
                        output.with_suffix(".html").write_text(to_html(rows, search_dirs), encoding="utf-8")
                except PermissionError as exc:
                    raise RuntimeError(
                        f"没有权限写入：\n{output}\n\n"
                        "请确认文件名不是文件夹，该文件没有在 Word/记事本中打开，"
                        "并且对输出文件夹有写入权限。"
                    ) from exc
                if self.mode.get() == "merge":
                    html_path = output.with_suffix(".html") if output.suffix.lower() != ".json" else None
                    note = f"请用浏览器打开：\n{html_path}" if html_path and html_path.exists() else ""
                    self.after(0, self.finish_success, len(rows), html_path or output, errors, note)
                    return
                if output.suffix.lower() == ".json":
                    self.after(0, self.finish_success, len(rows), output, errors)
                    return
                root = Path(self.input_path.get())
                root_name = root.name if root.is_dir() else root.parent.name
                shot_dirs = collect_shot_dirs(root)
                html_path = output.with_suffix(".html")
                note = f"请用浏览器打开：\n{html_path}" if html_path.exists() else ""
                try:
                    zip_paths = pack_output(output, shot_dirs, root_name)
                    first_zip = zip_paths[0] if zip_paths else output
                    if zip_paths:
                        zip_line = f"压缩包：\n{zip_paths[0]}"
                        if len(zip_paths) > 1:
                            zip_line += f"\n共 {len(zip_paths)} 个压缩包"
                        note = f"{note}\n\n{zip_line}" if note else zip_line
                    self.after(0, self.finish_success, len(rows), first_zip, errors, note)
                except Exception:
                    self.after(0, self.finish_success, len(rows), html_path if html_path.exists() else output, errors, note)
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
CJK_BREAK_CHARS = set("或和与及的了在从把被将由对且但因所以")
