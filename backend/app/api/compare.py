from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from typing import List, Optional
from sqlalchemy.orm import Session
import os
import json
import time
import xml.etree.ElementTree as ET
import html
import mimetypes
import shutil
import zipfile
from app.api.auth import get_current_active_user
from app.schemas.user import UserOut
from app.database import get_db

router = APIRouter(dependencies=[Depends(get_current_active_user)])

UPLOAD_DIR = "./static/uploads"
PREVIEW_DIR = "./static/preview"

_MEMORY_TASKS = {}
_MEMORY_DIFFS = {}
_MEMORY_NEXT_ID = [1000]
_MEMORY_FILES = {}  # task_id -> {file_a_path, file_b_path, file_a_name, file_b_name}

_ALIGN_CACHE = {}


def _require_compare_task_access(db: Session, task_id: int, current_user: UserOut):
    memory_task = _MEMORY_TASKS.get(task_id)
    if memory_task is not None:
        if current_user.role != "admin" and memory_task.get("user_id") != current_user.id:
            raise HTTPException(status_code=404, detail="Task not found")
        return "memory", memory_task

    try:
        from app.crud.compare import get_compare_task
        task = get_compare_task(db, task_id=task_id)
    except Exception:
        task = None

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if current_user.role != "admin" and getattr(task, "user_id", None) != current_user.id:
        raise HTTPException(status_code=404, detail="Task not found")
    return "db", task


def _ensure_upload_dir():
    if not os.path.exists(UPLOAD_DIR):
        os.makedirs(UPLOAD_DIR, exist_ok=True)


def _ensure_preview_dir():
    if not os.path.exists(PREVIEW_DIR):
        os.makedirs(PREVIEW_DIR, exist_ok=True)


_TEXT_PREVIEW_EXTS = {".md", ".markdown", ".txt", ".dita", ".xml", ".ditamap"}
_ZIP_TEXT_EXTS = {".dita", ".xml", ".ditamap", ".md", ".markdown", ".txt"}


def _file_ext(name):
    return os.path.splitext(name or "")[1].lower()


def _preview_kind(file_name):
    ext = _file_ext(file_name)
    if ext == ".pdf":
        return "pdf"
    if ext in {".docx", ".zip"}:
        return "html"
    if ext in {".md", ".markdown", ".txt"}:
        return "textdiff"
    if ext in _TEXT_PREVIEW_EXTS or ext == ".doc":
        return "html"
    return "html"


def _pdf_page_count(path):
    import fitz
    doc = fitz.open(path)
    try:
        return int(doc.page_count or 0)
    finally:
        doc.close()


def _join_pdf_tokens(tokens):
    import re
    out = ""
    for t in tokens:
        t = (t or "").strip()
        if not t:
            continue
        if not out:
            out = t
            continue
        if re.search(r'[\u4e00-\u9fff]$', out) or re.search(r'^[\u4e00-\u9fff]', t):
            out += t
        else:
            out += " " + t
    return out


def _norm_pdf_line(text):
    import re
    return re.sub(r"\s+", "", text or "").strip()


def _inflate_bbox(bbox, pad=1.6):
    x0, y0, x1, y1 = bbox
    return (x0 - pad, y0 - pad, x1 + pad, y1 + pad)


def _union_bbox(bboxes):
    xs0, ys0, xs1, ys1 = [], [], [], []
    for b in bboxes:
        if not b or len(b) < 4:
            continue
        xs0.append(b[0]); ys0.append(b[1]); xs1.append(b[2]); ys1.append(b[3])
    if not xs0:
        return None
    return (min(xs0), min(ys0), max(xs1), max(ys1))


def _extract_page_lines(page):
    lines = []
    words = page.get_text("words") or []
    if words:
        current_key = None
        current = None
        for w in words:
            x0, y0, x1, y1, text = w[:5]
            block_no = w[5] if len(w) > 5 else 0
            line_no = w[6] if len(w) > 6 else 0
            key = (block_no, line_no)
            item = {"text": text or "", "bbox": (x0, y0, x1, y1)}
            if key != current_key:
                if current:
                    current["text"] = _join_pdf_tokens([x["text"] for x in current["words"]])
                    current["bbox"] = _union_bbox([x["bbox"] for x in current["words"]])
                    if current["text"]:
                        lines.append(current)
                current_key = key
                current = {"text": "", "words": [item], "bbox": item["bbox"]}
            else:
                current["words"].append(item)
        if current:
            current["text"] = _join_pdf_tokens([x["text"] for x in current["words"]])
            current["bbox"] = _union_bbox([x["bbox"] for x in current["words"]])
            if current["text"]:
                lines.append(current)
        return lines

    d = page.get_text("dict") or {}
    for block in d.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = line.get("spans") or []
            word_list = []
            for s in spans:
                t = (s.get("text") or "").strip()
                if not t:
                    continue
                word_list.append({"text": t, "bbox": tuple(s.get("bbox") or (0, 0, 0, 0))})
            text = _join_pdf_tokens([x["text"] for x in word_list])
            if not text:
                continue
            bbox = line.get("bbox") or _union_bbox([x["bbox"] for x in word_list])
            lines.append({"text": text, "bbox": bbox, "words": word_list})
    return lines


def _word_diff_boxes(line_a, line_b):
    from difflib import SequenceMatcher
    wa = line_a.get("words") or []
    wb = line_b.get("words") or []
    na = [_norm_pdf_line(w.get("text", "")) for w in wa]
    nb = [_norm_pdf_line(w.get("text", "")) for w in wb]
    if not any(na) and not any(nb):
        return [], []
    sm = SequenceMatcher(None, na, nb, autojunk=False)
    boxes_a, boxes_b = [], []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        if tag in ("delete", "replace"):
            boxes_a.extend(w["bbox"] for w in wa[i1:i2] if w.get("bbox"))
        if tag in ("insert", "replace"):
            boxes_b.extend(w["bbox"] for w in wb[j1:j2] if w.get("bbox"))
    return boxes_a, boxes_b


def _pack_words(words):
    text = ""
    spans = []
    for w in words or []:
        token = _norm_pdf_line(w.get("text", ""))
        if not token:
            continue
        start = len(text)
        text += token
        spans.append((start, len(text), w.get("bbox")))
    return text, spans


def _spans_in_range(spans, start, end):
    boxes = []
    for s, e, bbox in spans:
        if bbox and e > start and s < end:
            boxes.append(bbox)
    return boxes


def _hunk_diff_boxes(lines_a, lines_b):
    import re
    from difflib import SequenceMatcher
    wa, wb = [], []
    for line in lines_a or []:
        wa.extend(line.get("words") or [])
    for line in lines_b or []:
        wb.extend(line.get("words") or [])
    sa, spa = _pack_words(wa)
    sb, spb = _pack_words(wb)
    if not sa and not sb:
        return [], []
    if re.fullmatch(r"\d{1,4}", sa or "") and re.fullmatch(r"\d{1,4}", sb or ""):
        return [], []
    ratio = SequenceMatcher(None, sa, sb).ratio() if (sa or sb) else 0.0
    similar = ratio >= 0.45
    sm = SequenceMatcher(None, sa, sb, autojunk=False)
    boxes_a, boxes_b = [], []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        if tag == "replace":
            kind_a = "chg" if similar else "del"
            kind_b = "chg" if similar else "ins"
            boxes_a.extend((b, kind_a) for b in _spans_in_range(spa, i1, i2))
            boxes_b.extend((b, kind_b) for b in _spans_in_range(spb, j1, j2))
        elif tag == "delete":
            boxes_a.extend((b, "del") for b in _spans_in_range(spa, i1, i2))
        elif tag == "insert":
            boxes_b.extend((b, "ins") for b in _spans_in_range(spb, j1, j2))
    if similar:
        if not boxes_a and not boxes_b:
            return [], []
    else:
        if not boxes_a:
            boxes_a = [(ln.get("bbox"), "del") for ln in (lines_a or []) if ln.get("bbox")]
        if not boxes_b:
            boxes_b = [(ln.get("bbox"), "ins") for ln in (lines_b or []) if ln.get("bbox")]
    return boxes_a, boxes_b


def _diff_page_boxes(page_a, page_b, for_side):
    from difflib import SequenceMatcher
    lines_a = _extract_page_lines(page_a)
    lines_b = _extract_page_lines(page_b)
    na = [_norm_pdf_line(x["text"]) for x in lines_a]
    nb = [_norm_pdf_line(x["text"]) for x in lines_b]
    sm = SequenceMatcher(None, na, nb, autojunk=False)
    boxes = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        if tag == "delete" and for_side == "a":
            for line in lines_a[i1:i2]:
                if line.get("bbox"):
                    boxes.append((line["bbox"], "del"))
        elif tag == "insert" and for_side == "b":
            for line in lines_b[j1:j2]:
                if line.get("bbox"):
                    boxes.append((line["bbox"], "ins"))
        elif tag == "replace":
            ba, bb = _hunk_diff_boxes(lines_a[i1:i2], lines_b[j1:j2])
            boxes.extend(ba if for_side == "a" else bb)
    try:
        from app.utils.compare_preview import extra_page_boxes
        boxes.extend(extra_page_boxes(page_a, page_b, for_side))
    except Exception:
        pass
    return boxes


def _paint_highlights(png_bytes, width, height, boxes, zoom):
    import io
    from PIL import Image, ImageDraw
    colors = {
        "del": (255, 76, 76, 92),
        "ins": (46, 184, 92, 92),
        "chg": (255, 196, 0, 100),
        "img": (59, 130, 246, 96),
        "fmt": (168, 85, 247, 96),
    }
    img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for bbox, kind in boxes:
        color = colors.get(kind)
        if not color or not bbox:
            continue
        x0, y0, x1, y1 = _inflate_bbox(bbox)
        rect = [x0 * zoom, y0 * zoom, x1 * zoom, y1 * zoom]
        if rect[2] <= rect[0] or rect[3] <= rect[1]:
            continue
        draw.rectangle(rect, fill=color)
    out = Image.alpha_composite(img, overlay).convert("RGB")
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()


def _render_pdf_page_png(path, page, zoom=1.5, peer_path="", peer_page=0, side="a", highlight=True):
    import fitz
    doc = fitz.open(path)
    try:
        total = int(doc.page_count or 0)
        if total <= 0:
            raise ValueError("PDF has no pages")
        idx = max(1, min(int(page), total)) - 1
        this_page = doc[idx]
        boxes = []
        if highlight and peer_path and os.path.exists(peer_path) and _file_ext(peer_path) == ".pdf":
            peer = fitz.open(peer_path)
            try:
                ptotal = int(peer.page_count or 0)
                if ptotal > 0:
                    pidx = max(1, min(int(peer_page or page), ptotal)) - 1
                    if side == "b":
                        boxes = _diff_page_boxes(peer[pidx], this_page, "b")
                    else:
                        boxes = _diff_page_boxes(this_page, peer[pidx], "a")
            finally:
                peer.close()
        pix = this_page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        png = pix.tobytes("png")
        if boxes:
            png = _paint_highlights(png, pix.width, pix.height, boxes, zoom)
        return png, total
    finally:
        doc.close()


def _heading_key(text):
    import re
    s = (text or "").strip()
    s = re.sub(r"^第\s*[一二三四五六七八九十百零\d]+\s*[章节篇]\s*", "", s)
    s = re.sub(r"^[A-Za-z]?\d+(?:\.\d+)*\s*", "", s)
    s = re.sub(r"\s+", "", s)
    return s.lower()


def _front_page_heading(page):
    import re
    text = page.get_text() or ""
    if "此页有意留白" in text or "intentionally left blank" in text.lower():
        return "空白页"
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    skip = re.compile(r"^(?:[IVXivx]+|\d+|[—\-–]+)$")
    for ln in lines[:12]:
        if skip.match(ln):
            continue
        if ln in ("产品说明书", "使用说明书"):
            return "封面"
        if "关于说明书" in ln:
            return "关于说明书"
        if ln.startswith("版本记录") or ln == "版本记录":
            return "版本记录"
        if ln in ("目录", "CONTENTS", "Contents") or ln.startswith("目录"):
            return "目录"
        if len(ln) <= 24 and not ln.endswith("。"):
            return ln
    return "封面"


def _front_matter_ranges(doc, last_page):
    last_page = int(last_page or 0)
    n = int(doc.page_count or 0)
    last_page = min(last_page, n)
    if last_page < 1:
        return []
    ranges = []
    current = None
    for i in range(last_page):
        page_no = i + 1
        heading = _front_page_heading(doc[i])
        if current and current["heading"] == heading:
            current["page_end"] = page_no
            continue
        if current:
            ranges.append(current)
        current = {
            "heading": heading,
            "level": 0,
            "page_start": page_no,
            "page_end": page_no,
        }
    if current:
        ranges.append(current)
    return ranges


def _pdf_chapter_ranges(path):
    import fitz
    doc = fitz.open(path)
    try:
        toc = doc.get_toc() or []
        n = int(doc.page_count or 0)
        ranges = []
        if toc and len(toc) >= 2:
            for i, item in enumerate(toc):
                level = int(item[0] or 1)
                title = str(item[1] or "").strip()
                page = int(item[2] or 1)
                if not title or n <= 0:
                    continue
                page = max(1, min(page, n))
                end = n
                for j in range(i + 1, len(toc)):
                    if int(toc[j][0] or 1) <= level:
                        end = int(toc[j][2] or 1) - 1
                        break
                end = max(page, min(end, n))
                ranges.append({
                    "heading": title,
                    "level": level,
                    "page_start": page,
                    "page_end": end,
                })
        elif n:
            pages_text = [(doc[i].get_text() or "") for i in range(n)]
            from app.utils.doc_parser import detect_headings_from_text, flatten_chapters
            flat = flatten_chapters(detect_headings_from_text(pages_text))
            for ch in flat:
                heading = (ch.get("heading") or "").strip()
                ps = int(ch.get("page_start") or 0)
                pe = int(ch.get("page_end") or ps)
                if not heading or ps <= 0:
                    continue
                ranges.append({
                    "heading": heading,
                    "level": 1,
                    "page_start": ps,
                    "page_end": max(ps, pe),
                })
        first_body = min((int(r.get("page_start") or 0) for r in ranges if int(r.get("page_start") or 0) > 0), default=0)
        if first_body > 1:
            ranges = _front_matter_ranges(doc, first_body - 1) + ranges
        return ranges
    finally:
        doc.close()


def _align_chapter_ranges(ranges_a, ranges_b):
    from difflib import SequenceMatcher
    used = set()
    pairs = []
    keys_b = {}
    for j, rb in enumerate(ranges_b):
        keys_b.setdefault(_heading_key(rb.get("heading", "")), []).append(j)

    n_a = max(1, len(ranges_a) - 1)
    n_b = max(1, len(ranges_b) - 1)
    for i, ra in enumerate(ranges_a):
        key = _heading_key(ra.get("heading", ""))
        if not key:
            continue
        cand = [j for j in keys_b.get(key, []) if j not in used]
        chosen = None
        if len(cand) == 1:
            chosen = cand[0]
        elif cand:
            pos = i / n_a
            chosen = min(cand, key=lambda j: abs(j / n_b - pos))
        else:
            best_j, best = None, 0.0
            for j, rb in enumerate(ranges_b):
                if j in used:
                    continue
                kb = _heading_key(rb.get("heading", ""))
                if not kb:
                    continue
                score = SequenceMatcher(None, key, kb).ratio()
                if score > best:
                    best, best_j = score, j
            if best_j is not None and best >= 0.72:
                chosen = best_j
        if chosen is None:
            continue
        used.add(chosen)
        rb = ranges_b[chosen]
        pairs.append({
            "heading_a": ra.get("heading", ""),
            "heading_b": rb.get("heading", ""),
            "level": max(int(ra.get("level") or 1), int(rb.get("level") or 1)),
            "page_start_a": int(ra.get("page_start") or 0),
            "page_end_a": int(ra.get("page_end") or 0),
            "page_start_b": int(rb.get("page_start") or 0),
            "page_end_b": int(rb.get("page_end") or 0),
        })
    return pairs


def _lookup_peer_page(pairs, page, from_side):
    sa, sb = ("b", "a") if from_side == "b" else ("a", "b")
    containing = []
    for item in pairs or []:
        start = int(item.get(f"page_start_{sa}") or 0)
        end = int(item.get(f"page_end_{sa}") or 0)
        peer_start = int(item.get(f"page_start_{sb}") or 0)
        if start and end and peer_start and start <= page <= end:
            containing.append(item)
    if not containing:
        return 0, ""
    containing.sort(key=lambda item: (
        int(item.get(f"page_end_{sa}") or 0) - int(item.get(f"page_start_{sa}") or 0),
        -int(item.get("level") or 0),
    ))
    item = containing[0]
    offset = page - int(item.get(f"page_start_{sa}") or page)
    peer_start = int(item.get(f"page_start_{sb}") or 0)
    peer_end = int(item.get(f"page_end_{sb}") or peer_start)
    peer = min(peer_end, max(peer_start, peer_start + offset))
    heading = item.get(f"heading_{sa}") or item.get(f"heading_{sb}") or ""
    return peer, heading


def _align_cache_key(path_a, path_b):
    try:
        return (path_a, path_b, os.path.getmtime(path_a), os.path.getmtime(path_b))
    except OSError:
        return (path_a, path_b, 0, 0)


def _get_preview_align(task_id):
    path_a, _ = _resolve_preview_file(task_id, "a")
    path_b, _ = _resolve_preview_file(task_id, "b")
    if not path_a or not path_b:
        return {"pairs": []}
    if _file_ext(path_a) != ".pdf" or _file_ext(path_b) != ".pdf":
        return {"pairs": []}
    key = _align_cache_key(path_a, path_b)
    cached = _ALIGN_CACHE.get(key)
    if cached is not None:
        return cached
    pairs = _align_chapter_ranges(_pdf_chapter_ranges(path_a), _pdf_chapter_ranges(path_b))
    data = {"pairs": pairs}
    _ALIGN_CACHE[key] = data
    return data


def _copy_preview_source(src_path, task_id, side, file_name):
    if not src_path or not os.path.exists(src_path):
        return ""
    ext = _file_ext(file_name) or _file_ext(src_path) or ".bin"
    dest = os.path.join(PREVIEW_DIR, f"task_{task_id}_{side}{ext}")
    shutil.copy2(src_path, dest)
    return dest


def _resolve_preview_file(task_id, side):
    side = "b" if side == "b" else "a"
    if task_id in _MEMORY_FILES:
        info = _MEMORY_FILES[task_id]
        path = info.get(f"file_{side}_path", "")
        name = info.get(f"file_{side}_name", "")
        if path and os.path.exists(path):
            return path, name
    if os.path.isdir(PREVIEW_DIR):
        prefix = f"task_{task_id}_{side}."
        for fname in os.listdir(PREVIEW_DIR):
            if fname.startswith(prefix):
                path = os.path.join(PREVIEW_DIR, fname)
                return path, fname
    return "", ""


def _read_text_preview(path, limit=200000):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read(limit)


def _wrap_pre(text):
    return f'<pre class="doc-preview">{html.escape(text or "")}</pre>'


def _build_zip_preview_html(path):
    with zipfile.ZipFile(path) as zf:
        names = [n for n in zf.namelist() if n and not n.endswith("/")][:200]
        items = "".join(f"<li>{html.escape(n)}</li>" for n in names)
        extra = ""
        preview_member = next(
            (n for n in names if _file_ext(n) in _ZIP_TEXT_EXTS),
            None,
        )
        if preview_member:
            raw = zf.read(preview_member)
            text = raw.decode("utf-8", errors="replace")[:80000]
            extra = (
                f"<h4>{html.escape(preview_member)}</h4>"
                f"{_wrap_pre(text)}"
            )
    return (
        '<div class="doc-preview-html">'
        f"<p>ZIP 内文件（最多 200）</p><ul>{items}</ul>{extra}"
        "</div>"
    )


def _build_compare_preview_html(path, file_name, peer_path="", peer_name="", side="a", highlight=False):
    ext = _file_ext(file_name) or _file_ext(path)
    try:
        if highlight and peer_path and os.path.exists(peer_path):
            try:
                from app.utils.compare_preview import build_highlighted_preview
                highlighted = build_highlighted_preview(
                    path, file_name, peer_path, peer_name, side
                )
                if highlighted:
                    return highlighted
            except Exception as e:
                print(f"[Preview] highlight failed: {e}")
        if ext == ".docx":
            try:
                from app.api.qa import _build_docx_preview_html
                return _build_docx_preview_html(path)
            except Exception:
                import docx2txt
                return _wrap_pre(docx2txt.process(path) or "")
        if ext == ".zip":
            return _build_zip_preview_html(path)
        if ext == ".doc":
            return _wrap_pre("当前预览支持 .docx / PDF / MD / TXT / DITA / ZIP / Excel，请将 .doc 另存为 .docx 后再预览。")
        if ext in {".xlsx", ".xlsm", ".xls"}:
            from app.api.qa import _build_xlsx_preview_html
            return _build_xlsx_preview_html(path)
        if ext in _TEXT_PREVIEW_EXTS:
            return _wrap_pre(_read_text_preview(path))
        return _wrap_pre(_read_text_preview(path))
    except Exception as e:
        return _wrap_pre(f"预览失败：{e}")


def _read_upload_as_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        return ""


def _extract_pdf(path: str) -> str:
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            return "\n".join((p.extract_text() or "") for p in pdf.pages)
    except Exception:
        try:
            from pypdf import PdfReader
            return "\n".join((p.extract_text() or "") for p in PdfReader(path).pages)
        except Exception:
            return _read_upload_as_text(path)


def _strip_ns(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _extract_dita_text(dita_file_path):
    """
    提取 DITA 文件中的句段。
    规则：
    - 表格按行拆分（每行一个句段，合并所有单元格文本）
    - 列表按项拆分（每项一个句段）
    - 提取文本标签：p、li、entry、note、title、shortdesc、step、cmd 等
    - 过滤空句段和纯空格句段
    - 过滤纯 XML 标签内容（如 ph、b、i、u 等内联标签不单独成句段）
    """
    try:
        tree = ET.parse(dita_file_path)
        root = tree.getroot()
        topic_id = root.attrib.get("id", "")
        title_el = root.find(".//title")
        title = (title_el.text or "").strip() if title_el is not None else ""
        
        segments = []
        if title:
            segments.append({"text": title, "tag": "title"})
        
        # 需要处理的文本标签
        block_tags = {"p", "li", "note", "step", "shortdesc", "cmd", "entry", 
                      "dt", "dd", "li", "stentry", "refsyn", "conbodydiv",
                      "section", "paragraph"}
        
        # 内联标签（不单独成句段）
        inline_tags = {"ph", "b", "i", "u", "strong", "em", "tt", "codeph",
                       "keyword", "tm", "sup", "sub", "xref", "linktext"}
        
        def get_text(elem, include_tail=True):
            """递归获取元素的文本内容，包括 tail"""
            parts = []
            if elem.text:
                parts.append(elem.text)
            for child in elem:
                if _strip_ns(child.tag) not in inline_tags:
                    parts.append(get_text(child))
                else:
                    if child.text:
                        parts.append(child.text)
                    if include_tail and child.tail:
                        parts.append(child.tail)
            if include_tail and elem.tail:
                parts.append(elem.tail)
            return "".join(parts).strip()
        
        def process_table(table_elem):
            """处理表格，按行拆分"""
            rows = table_elem.findall(".//tr")
            for row in rows:
                cells = row.findall(".//entry")
                if cells:
                    cell_texts = []
                    for cell in cells:
                        cell_text = get_text(cell)
                        if cell_text:
                            cell_texts.append(cell_text)
                    if cell_texts:
                        row_text = " | ".join(cell_texts)
                        if row_text.strip():
                            segments.append({"text": row_text, "tag": "table-row"})
        
        def process_list(list_elem, list_type="ul"):
            """处理列表，按项拆分"""
            items = list_elem.findall(f"./{list_type}/li") or list_elem.findall(".//li")
            for item in items:
                item_text = get_text(item)
                if item_text.strip():
                    segments.append({"text": item_text, "tag": "list-item"})
        
        def walk_elem(elem):
            """遍历元素并提取文本"""
            tag = _strip_ns(elem.tag)
            
            # 处理表格
            if tag in ("table", "simpletable"):
                process_table(elem)
                return
            
            # 处理列表
            if tag in ("ul", "ol", "sl"):
                process_list(elem, tag)
                return
            
            # 处理块级标签
            if tag in block_tags:
                text = get_text(elem)
                if text:
                    segments.append({"text": text, "tag": tag})
            
            # 处理图片
            if tag == "fig":
                caption_el = elem.find(".//title")
                if caption_el is not None and caption_el.text:
                    segments.append({"text": f"[图] {caption_el.text.strip()}", "tag": "fig"})
            
            # 递归处理子元素
            for child in elem:
                walk_elem(child)
        
        # 从 topic 或 concept/mainbody 开始遍历
        main_body = root.find(".//topic") or root.find(".//concept") or root.find(".//task") or root
        walk_elem(main_body)
        
        # 过滤空句段和纯空格句段
        segments = [s for s in segments if s["text"].strip()]
        
        # 去重，相邻重复的句段只保留一个
        deduped = []
        prev_text = None
        for s in segments:
            if s["text"] != prev_text:
                deduped.append(s)
                prev_text = s["text"]
        
        return topic_id, title, deduped
    except Exception as e:
        text = _read_upload_as_text(dita_file_path)
        return "", "", [{"text": text, "tag": "text"}]


def _parse_ditamap(ditamap_path, base_dir):
    """
    解析 ditamap，按文档顺序提取 topic 列表。
    每条记录: {level_path, navtitle, href, tag, topicref_type}
    支持单行 XML 格式（用 > 拼接的 topicref）。
    """
    topics = []
    
    try:
        tree = ET.parse(ditamap_path)
        root = tree.getroot()
    except Exception:
        return topics
    
    def walk(node, ancestors):
        tag = _strip_ns(node.tag)
        nav = (node.attrib.get("navtitle") or 
               node.attrib.get("{http://www.w3.org/ime/cms}title") or "")
        href = node.attrib.get("href", "")
        keys = node.attrib.get("keys", "")
        level_attr = node.attrib.get("level", "")
        type_attr = node.attrib.get("{http://www.w3.org/ime/cms}type") or node.attrib.get("type", "")
        
        path = ancestors + [nav] if nav else ancestors
        
        if href and href.endswith(".dita"):
            topics.append({
                "tag": tag,
                "navtitle": nav,
                "href": href,
                "path": path,
                "level": int(level_attr) if level_attr.isdigit() else len(path),
                "topic_type": type_attr or tag,
                "keys": keys,
            })
        
        for child in node:
            walk(child, path)
    
    walk(root, [])
    return topics


def _parse_dita_dir(path: str):
    """
    解析 DITA 目录，返回：
    {
        "ditamap_path": ...,
        "topics": [{"navtitle", "href", "file_path", "path", "level", "topic_id", "title", "segments"}],
        "all_segments": [...]  # 供 backward compat
    }
    """
    ditamap_files = []
    for root_dir, _, files in os.walk(path):
        for fn in files:
            if fn.lower().endswith(".ditamap"):
                ditamap_files.append(os.path.join(root_dir, fn))
    
    raw_topics = []
    ditamap_path = None
    if ditamap_files:
        ditamap_path = ditamap_files[0]
        base_dir = os.path.dirname(ditamap_path)
        raw_topics = _parse_ditamap(ditamap_path, base_dir)
    
    if not raw_topics:
        # 没找到 ditamap，按文件顺序处理所有 .dita
        for root_dir, _, files in os.walk(path):
            for fn in sorted(files):
                if fn.lower().endswith(".dita"):
                    raw_topics.append({
                        "tag": "topic",
                        "navtitle": fn.replace(".dita", ""),
                        "href": os.path.relpath(os.path.join(root_dir, fn), path),
                        "path": [fn.replace(".dita", "")],
                        "level": 1,
                        "topic_type": "topic",
                        "keys": "",
                    })
    
    topics = []
    for t in raw_topics:
        full_path = os.path.join(os.path.dirname(ditamap_path) if ditamap_path else path, t["href"])
        if not os.path.exists(full_path):
            full_path = os.path.join(path, t["href"])
        
        if os.path.exists(full_path):
            topic_id, title, segments = _extract_dita_text(full_path)
        else:
            topic_id, title, segments = "", t["navtitle"], []
        
        if not title:
            title = t["navtitle"]
        
        # 一级章节 = path[0] (如 "Device overview")
        # 小节 = 最后一个 navtitle
        chapter = t["path"][0] if len(t["path"]) >= 1 else title
        section = title or t["navtitle"]
        
        topics.append({
            "navtitle": t["navtitle"],
            "href": t["href"],
            "file_path": full_path,
            "path": t["path"],
            "level": t["level"],
            "topic_id": topic_id,
            "title": title,
            "topic_type": t["topic_type"],
            "chapter": chapter,
            "section": section,
            "segments": segments,
            "keys": t.get("keys", ""),
        })
    
    # 为 backward compat 也生成 all_segments
    all_segments = []
    for topic in topics:
        all_segments.append({
            "text": topic["title"],
            "chapter": topic["chapter"],
            "section": topic["section"],
            "level": topic["level"],
            "tag": "title",
            "topic_id": topic["topic_id"],
            "file_path": topic["file_path"],
        })
        for seg in topic["segments"]:
            if seg["text"] != topic["title"]:
                all_segments.append({
                    "text": seg["text"],
                    "chapter": topic["chapter"],
                    "section": topic["section"],
                    "level": topic["level"],
                    "tag": seg["tag"],
                    "topic_id": topic["topic_id"],
                    "file_path": topic["file_path"],
                })
    
    text_parts = []
    for topic in topics:
        text_parts.append(f"# {'#' * min(topic['level'], 6)} {topic['title']}")
        for seg in topic["segments"]:
            text_parts.append(seg["text"])
        text_parts.append("")
    
    return {
        "text": "\n".join(text_parts),
        "segments": all_segments,
        "topics": topics,
        "structure": topics,  # backward compat
        "ditamap_path": ditamap_path,
    }


def _extract_dita_dir(path: str):
    """backward compat wrapper"""
    return _parse_dita_dir(path)


def _simple_compare(text_a, text_b):
    from difflib import SequenceMatcher

    lines_a = [ln.strip() for ln in text_a.split("\n") if ln.strip()]
    lines_b = [ln.strip() for ln in text_b.split("\n") if ln.strip()]

    diffs = []
    matched_pairs = []
    matched_b = set()
    exact_match = 0
    
    for i, la in enumerate(lines_a):
        best_j = -1
        best_sim = 0.0
        for j, lb in enumerate(lines_b):
            if j in matched_b:
                continue
            sim = SequenceMatcher(None, la, lb).ratio()
            if sim > best_sim:
                best_sim = sim
                best_j = j
        if best_j >= 0:
            matched_b.add(best_j)
            if best_sim >= 0.99:
                exact_match += 1
            matched_pairs.append((i, best_j, best_sim, la, lines_b[best_j], "", ""))
            if best_sim < 0.85:
                diffs.append({
                    "diff_type": "modify",
                    "severity": "high" if best_sim < 0.7 else "medium",
                    "similarity": round(best_sim, 4),
                    "text_a": la,
                    "text_b": lines_b[best_j],
                    "position_a": {"line": i},
                    "position_b": {"line": best_j},
                    "chapter": "",
                    "section": "",
                })
        else:
            diffs.append({
                "diff_type": "delete",
                "severity": "medium",
                "similarity": 0.0,
                "text_a": la,
                "text_b": "",
                "position_a": {"line": i},
                "position_b": {},
                "chapter": "",
                "section": "",
            })
    
    matched_a = set(p[0] for p in matched_pairs)
    only_a = [(i, "", "") for i in range(len(lines_a)) if i not in matched_a]
    only_b = []
    
    for j, lb in enumerate(lines_b):
        if j not in matched_b:
            diffs.append({
                "diff_type": "add",
                "severity": "medium",
                "similarity": 0.0,
                "text_a": "",
                "text_b": lb,
                "position_a": {},
                "position_b": {"line": j},
                "chapter": "",
                "section": "",
            })
            only_b.append((j, "", ""))

    total = max(len(lines_a) + len(lines_b), 1)
    matched_count = (len(lines_a) + len(lines_b) - len(diffs))
    similarity = round(matched_count / total, 4) if total else 1.0
    if similarity > 1.0:
        similarity = 1.0

    stats = {
        "add": len([d for d in diffs if d["diff_type"] == "add"]),
        "delete": len([d for d in diffs if d["diff_type"] == "delete"]),
        "modify": len([d for d in diffs if d["diff_type"] == "modify"]),
    }
    verdict = "✅ 自动通过（≥80%）" if similarity >= 0.8 else ("⚠️ 建议复核（60% ~ 80%）" if similarity >= 0.6 else "🟥 强制人工复核（<60%，不可互换）")
    return {
        "similarity": similarity,
        "verdict": verdict,
        "total_diffs": len(diffs),
        "diff_stats": stats,
        "diffs": diffs,
        "exact_match": exact_match,
        "matched_pairs": matched_pairs,
        "only_a": only_a,
        "only_b": only_b,
        "n_a": len(lines_a),
        "n_b": len(lines_b),
    }


def _is_dita_package(filename: str) -> bool:
    """判断是否为 DITA 包（.zip 且包含 .ditamap）"""
    if not filename:
        return False
    ext = os.path.splitext(filename)[1].lower()
    return ext in (".zip", ".dita", ".ditamap")


def _parse_file(file_path: str, filename: str):
    ext = os.path.splitext(filename)[1].lower()
    if ext in (".pdf",):
        # 使用专门的 PDF 解析器
        try:
            from app.utils.doc_parser import parse_pdf
            result = parse_pdf(file_path)
            return {
                "text": result.get("full_text", ""),
                "segments": result.get("pages_text", []),
                "structure": result.get("chapters", []),
                "type": "pdf",
                "chapters": result.get("chapters", [])
            }
        except Exception as e:
            print(f"PDF parse error: {e}")
            text = _extract_pdf(file_path)
            return {"text": text, "segments": [], "structure": [], "type": "pdf"}
    elif ext in (".docx", ".doc"):
        # 使用 Word 解析器
        try:
            from app.utils.doc_parser import parse_docx
            result = parse_docx(file_path)
            return {
                "text": result.get("full_text", ""),
                "segments": result.get("paragraphs", []),
                "structure": result.get("chapters", []),
                "type": "docx",
                "chapters": result.get("chapters", [])
            }
        except Exception as e:
            print(f"DOCX parse error: {e}")
            text = _read_upload_as_text(file_path)
            return {"text": text, "segments": [], "structure": [], "type": "docx"}
    elif ext in (".md", ".markdown"):
        # 使用 Markdown 解析器
        try:
            from app.utils.doc_parser import parse_markdown
            result = parse_markdown(file_path)
            return {
                "text": result.get("full_text", ""),
                "segments": [],
                "structure": result.get("chapters", []),
                "type": "md",
                "chapters": result.get("chapters", [])
            }
        except Exception as e:
            print(f"MD parse error: {e}")
            text = _read_upload_as_text(file_path)
            return {"text": text, "segments": [], "structure": [], "type": "md"}
    elif ext in (".dita", ".ditamap"):
        result = _extract_dita_dir(file_path)
        if isinstance(result, str):
            return {"text": result, "segments": [], "structure": [], "type": "dita"}
        result["type"] = "dita"
        return result
    elif ext == ".zip":
        import zipfile
        temp_dir = os.path.join(UPLOAD_DIR, f"tmp_{int(time.time()*1000)}_{os.path.basename(filename).replace('.zip','')}")
        os.makedirs(temp_dir, exist_ok=True)
        try:
            with zipfile.ZipFile(file_path, 'r') as zf:
                zf.extractall(temp_dir)
            result = _extract_dita_dir(temp_dir)
            if isinstance(result, str):
                return {"text": result, "segments": [], "structure": [], "type": "dita", "temp_dir": temp_dir}
            result["type"] = "dita"
            result["temp_dir"] = temp_dir
            return result
        except Exception:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
            return {"text": "", "segments": [], "structure": [], "type": "unknown"}
    elif ext in (".xlsx", ".xlsm", ".xls"):
        try:
            from app.utils.document_parser import parse_xlsx
            text = parse_xlsx(file_path)
            return {"text": text or "", "segments": [], "structure": [], "type": "xlsx"}
        except Exception as e:
            print(f"XLSX parse error: {e}")
            return {"text": "", "segments": [], "structure": [], "type": "xlsx"}
    else:
        text = _read_upload_as_text(file_path)
        return {"text": text, "segments": [], "structure": [], "type": "text"}


def _do_single_compare(file_a_path, file_b_path, file_a_name, file_b_name, user_id: int, group_id=None, file_names=None, db=None):
    task_id = None
    parsed_a = _parse_file(file_a_path, file_a_name)
    parsed_b = _parse_file(file_b_path, file_b_name)

    text_a = parsed_a["text"] if isinstance(parsed_a, dict) else parsed_a
    text_b = parsed_b["text"] if isinstance(parsed_b, dict) else parsed_b

    segments_a = parsed_a.get("segments", []) if isinstance(parsed_a, dict) else []
    segments_b = parsed_b.get("segments", []) if isinstance(parsed_b, dict) else []
    structure_a = parsed_a.get("structure", []) if isinstance(parsed_a, dict) else []
    structure_b = parsed_b.get("structure", []) if isinstance(parsed_b, dict) else []

    is_dita = (
        parsed_a.get("type") == "dita" and parsed_b.get("type") == "dita"
        and parsed_a.get("topics") and parsed_b.get("topics")
    )

    result = None
    dita_full = None
    if is_dita:
        try:
            from app.utils.dita_compare import compare_dita_packages
            dita_full = compare_dita_packages(
                parsed_a.get("temp_dir") or os.path.dirname(parsed_a.get("ditamap_path", "")),
                parsed_b.get("temp_dir") or os.path.dirname(parsed_b.get("ditamap_path", "")),
                threshold=0.80,
            )
            diffs = []
            for tr in dita_full.get("topics", []):
                for d in tr.get("diffs", []):
                    diffs.append({
                        "diff_type": d.get("type", "modify"),
                        "severity": (
                            "high" if d.get("type") in ("only_a", "only_b")
                            else "medium" if d.get("similarity", 0) < 0.7
                            else "low"
                        ),
                        "similarity": float(d.get("similarity", 0.0)),
                        "text_a": d.get("text_a", ""),
                        "text_b": d.get("text_b", ""),
                        "position_a": {},
                        "position_b": {},
                        "chapter": tr.get("chapter_a", "") or tr.get("chapter_b", ""),
                    })
            result = {
                "similarity": dita_full.get("overall_jaccard", 0.0),
                "verdict": (
                    "自动通过（>=80%）" if dita_full.get("overall_jaccard", 0.0) >= 0.80
                    else "建议复核（60% ~ 80%）" if dita_full.get("overall_jaccard", 0.0) >= 0.60
                    else "强制人工复核（<60%，不可互换）"
                ),
                "total_diffs": sum(tr.get("n_diffs", 0) for tr in dita_full.get("topics", [])),
                "diff_stats": {
                    "add": dita_full.get("n_only_b", 0),
                    "delete": dita_full.get("n_only_a", 0),
                    "modify": dita_full.get("stat_low", 0) + dita_full.get("stat_partial", 0),
                },
                "diffs": diffs,
                "exact_match": dita_full.get("n_exact", 0),
                "matched_pairs": [],
                "only_a": [{"chapter": tr.get("chapter_a", ""), "section": tr.get("navtitle", "")}
                           for tr in dita_full.get("topics", []) if tr.get("type") == "only_a"],
                "only_b": [{"chapter": tr.get("chapter_b", ""), "section": tr.get("navtitle", "")}
                           for tr in dita_full.get("topics", []) if tr.get("type") == "only_b"],
                "n_a": dita_full.get("n_sentences_a", 0),
                "n_b": dita_full.get("n_sentences_b", 0),
                "dita_full": dita_full,
            }
        except Exception as e:
            is_dita = False
            print(f"[DITA对比失败] 走通用对比: {e}")

    is_doc = (
        parsed_a.get("type") in ("docx", "pdf", "md") and
        parsed_b.get("type") in ("docx", "pdf", "md")
    )

    doc_full = None
    if is_doc and result is None:
        try:
            from app.utils.doc_parser import compare_documents_by_format
            doc_full = compare_documents_by_format(file_a_path, file_b_path)
            diffs = []
            for r in doc_full.get("results", []):
                for d in r.get("diffs", []):
                    diffs.append({
                        "diff_type": "modify",
                        "severity": "low",
                        "similarity": d.get("score", 0.0),
                        "text_a": d.get("a", ""),
                        "text_b": d.get("b", ""),
                        "position_a": {},
                        "position_b": {},
                        "chapter": r.get("heading", ""),
                    })
            stats = doc_full.get("stats", {})
            result = {
                "similarity": stats.get("overall_sim", 0.0),
                "verdict": (
                    "自动通过（>=80%）" if stats.get("overall_sim", 0.0) >= 0.80
                    else "建议复核（60% ~ 80%）" if stats.get("overall_sim", 0.0) >= 0.60
                    else "强制人工复核（<60%，不可互换）"
                ),
                "total_diffs": len(diffs),
                "diff_stats": {
                    "add": stats.get("n_only_b", 0),
                    "delete": stats.get("n_only_a", 0),
                    "modify": stats.get("n_low", 0),
                },
                "diffs": diffs,
                "exact_match": 0,
                "matched_pairs": [],
                "only_a": [{"chapter": r.get("heading", ""), "section": r.get("heading", "")}
                           for r in doc_full.get("results", []) if r.get("status") == "仅在A中"],
                "only_b": [{"chapter": r.get("heading", ""), "section": r.get("heading", "")}
                           for r in doc_full.get("results", []) if r.get("status") == "仅在B中"],
                "n_a": len(doc_full.get("results", [])),
                "n_b": len(doc_full.get("results", [])),
                "doc_full": doc_full,
            }
        except Exception as e:
            print(f"[文档对比失败] 走通用对比: {e}")
            import traceback
            traceback.print_exc()

    if result is None:
        try:
            from app.utils.compare_utils import compare_documents
            result = compare_documents(text_a, text_b, {
                "segments_a": segments_a,
                "segments_b": segments_b,
                "structure_a": structure_a,
                "structure_b": structure_b,
            })
        except Exception:
            result = _simple_compare(text_a, text_b)

    try:
        from app.crud.compare import create_compare_task, update_compare_task, create_compare_diff
        task = create_compare_task(db, file_a_name, file_b_name, user_id, group_id=group_id, file_names=file_names)
        doc_full_json = json.dumps(doc_full, ensure_ascii=False) if doc_full else ""
        dita_full_json = json.dumps(dita_full, ensure_ascii=False) if dita_full else doc_full_json
        update_compare_task(
            db, task.id,
            result["similarity"], result["verdict"],
            result["total_diffs"], result["diff_stats"],
            result.get("exact_match", 0),
            result.get("n_a", 0),
            result.get("n_b", 0),
            result.get("matched_pairs", []),
            result.get("only_a", []),
            result.get("only_b", []),
            dita_full_json=dita_full_json,
        )
        diffs_to_save = result["diffs"][:200]
        if dita_full:
            for tr in dita_full.get("topics", []):
                for d in tr.get("diffs", []):
                    if len(diffs_to_save) >= 200:
                        break
                    diffs_to_save.append({
                        "diff_type": d.get("type", "modify"),
                        "severity": (
                            "high" if d.get("type") in ("only_a", "only_b")
                            else "medium" if d.get("similarity", 0) < 0.7
                            else "low"
                        ),
                        "similarity": float(d.get("similarity", 0.0)),
                        "text_a": d.get("text_a", ""),
                        "text_b": d.get("text_b", ""),
                        "position_a": {},
                        "position_b": {},
                        "chapter": tr.get("chapter_a", "") or tr.get("chapter_b", ""),
                    })
                if len(diffs_to_save) >= 200:
                    break

        for diff in diffs_to_save[:200]:
            try:
                create_compare_diff(
                    db, task.id,
                    diff.get("diff_type", "modify"),
                    diff.get("severity", "medium"),
                    float(diff.get("similarity", 0.0)),
                    diff.get("text_a", ""),
                    diff.get("text_b", ""),
                    diff.get("position_a") or {},
                    diff.get("position_b") or {},
                    diff.get("chapter", ""),
                )
            except Exception:
                continue
        task_id = task.id
    except Exception:
        task_id = _MEMORY_NEXT_ID[0]
        _MEMORY_NEXT_ID[0] += 1
        dita_full_json = json.dumps(dita_full, ensure_ascii=False) if dita_full else ""
        _MEMORY_TASKS[task_id] = {
            "id": task_id,
            "file_a_name": file_a_name,
            "file_b_name": file_b_name,
            "similarity": result["similarity"],
            "verdict": result["verdict"],
            "total_diffs": result["total_diffs"],
            "diff_stats": json.dumps(result["diff_stats"]),
            "status": "completed",
            "user_id": user_id,
            "created_at": int(time.time()),
            "exact_match": result.get("exact_match", 0),
            "n_a": result.get("n_a", 0),
            "n_b": result.get("n_b", 0),
            "matched_pairs": json.dumps(result.get("matched_pairs", [])),
            "only_a": json.dumps(result.get("only_a", [])),
            "only_b": json.dumps(result.get("only_b", [])),
            "dita_full": dita_full_json,
        }
        _MEMORY_DIFFS[task_id] = result["diffs"][:200]

    _ensure_preview_dir()
    preview_a_path = ""
    preview_b_path = ""
    try:
        preview_a_path = _copy_preview_source(file_a_path, task_id, "a", file_a_name)
        preview_b_path = _copy_preview_source(file_b_path, task_id, "b", file_b_name)
    except Exception as e:
        print(f"[Preview] Save preview files failed: {e}")

    _MEMORY_FILES[task_id] = {
        "file_a_path": preview_a_path,
        "file_b_path": preview_b_path,
        "file_a_name": file_a_name,
        "file_b_name": file_b_name,
    }

    return {
        "task_id": task_id,
        "comparison_id": task_id,
        "file_a_name": file_a_name,
        "file_b_name": file_b_name,
        "similarity": result["similarity"],
        "verdict": result["verdict"],
        "total_diffs": result["total_diffs"],
        "diff_stats": result["diff_stats"],
        "diffs": result["diffs"][:200],
        "exact_match": result.get("exact_match", 0),
        "n_a": result.get("n_a", 0),
        "n_b": result.get("n_b", 0),
        "is_dita": is_dita,
        "is_doc": is_doc,
        "dita_full": dita_full,
        "doc_full": doc_full,
        "has_preview": bool(preview_a_path or preview_b_path),
    }


@router.post("/")
async def create_compare(
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: UserOut = Depends(get_current_active_user),
):
    _ensure_upload_dir()

    if not files or len(files) < 2:
        raise HTTPException(status_code=400, detail="At least 2 files are required for comparison")

    saved_paths = []
    saved_names = []
    group_id = int(time.time() * 1000)

    for f in files:
        path = os.path.join(UPLOAD_DIR, f"{group_id}_{len(saved_paths)}_{f.filename}")
        try:
            with open(path, "wb") as buffer:
                buffer.write(await f.read())
            saved_paths.append(path)
            saved_names.append(f.filename)
        except Exception:
            for p in saved_paths:
                try: os.remove(p)
                except Exception: pass
            raise HTTPException(status_code=500, detail="File upload failed")

    ref_path = saved_paths[0]
    ref_name = saved_names[0]
    all_results = []

    for i in range(1, len(saved_paths)):
        cmp_path = saved_paths[i]
        cmp_name = saved_names[i]
        pair_result = _do_single_compare(
            ref_path, cmp_path, ref_name, cmp_name,
            user_id=current_user.id,
            group_id=group_id, file_names=json.dumps(saved_names, ensure_ascii=False),
            db=db,
        )
        all_results.append(pair_result)

    for p in saved_paths:
        try: os.remove(p)
        except Exception: pass

    return {
        "group_id": group_id,
        "file_count": len(files),
        "file_names": saved_names,
        "results": all_results,
    }


@router.get("/")
async def read_compare_tasks(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: UserOut = Depends(get_current_active_user),
):
    items = []
    
    db_tasks = []
    try:
        from app.crud.compare import get_compare_tasks
        db_tasks = get_compare_tasks(
            db,
            user_id=None if current_user.role == "admin" else current_user.id,
            skip=0,
            limit=1000,
        ) or []
    except Exception:
        pass
    
    for t in db_tasks:
        items.append({
            "id": t.id,
            "task_type": getattr(t, "task_type", "doc") or "doc",
            "file_a_name": getattr(t, "file_a_name", ""),
            "file_b_name": getattr(t, "file_b_name", ""),
            "similarity": getattr(t, "similarity", 0.0),
            "verdict": getattr(t, "verdict", ""),
            "total_diffs": getattr(t, "total_diffs", 0),
            "status": getattr(t, "status", "completed"),
            "user_id": getattr(t, "user_id", 1),
            "created_at": getattr(t, "created_at", None),
        })

    mem_list = sorted(_MEMORY_TASKS.values(), key=lambda x: -x["id"])
    for m in mem_list:
        if current_user.role != "admin" and m.get("user_id") != current_user.id:
            continue
        exists = any(item["id"] == m["id"] for item in items)
        if not exists:
            items.append({
                "id": m["id"],
                "file_a_name": m["file_a_name"],
                "file_b_name": m["file_b_name"],
                "similarity": m["similarity"],
                "verdict": m["verdict"],
                "total_diffs": m["total_diffs"],
                "status": m["status"],
                "user_id": m["user_id"],
                "created_at": m["created_at"],
            })

    items.sort(key=lambda x: x["id"] if isinstance(x["id"], int) else 0, reverse=True)
    
    return items[skip: skip + limit]


@router.get("/{task_id}")
async def read_compare(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: UserOut = Depends(get_current_active_user),
):
    source, access_obj = _require_compare_task_access(db, task_id, current_user)
    task_obj = None
    diffs = []
    matched_pairs = []
    only_a = []
    only_b = []

    try:
        from app.crud.compare import get_compare_task, get_compare_diffs
        task = access_obj if source == "db" else None
        if task is not None:
            task_obj = {
                "id": task.id,
                "task_type": getattr(task, "task_type", "doc") or "doc",
                "file_a_name": getattr(task, "file_a_name", ""),
                "file_b_name": getattr(task, "file_b_name", ""),
                "similarity": getattr(task, "similarity", 0.0),
                "verdict": getattr(task, "verdict", ""),
                "total_diffs": getattr(task, "total_diffs", 0),
                "diff_stats": getattr(task, "diff_stats", None),
                "status": getattr(task, "status", "completed"),
                "user_id": getattr(task, "user_id", 1),
                "created_at": getattr(task, "created_at", None),
                "exact_match": getattr(task, "exact_match", 0),
                "n_a": getattr(task, "n_a", 0),
                "n_b": getattr(task, "n_b", 0),
                "matched_pairs": getattr(task, "matched_pairs", "[]"),
                "only_a": getattr(task, "only_a", "[]"),
                "only_b": getattr(task, "only_b", "[]"),
                "dita_full": getattr(task, "dita_full", "") or "",
            }
            db_diffs = get_compare_diffs(db, task_id=task_id) or []
            for d in db_diffs:
                diffs.append({
                    "id": getattr(d, "id", 0),
                    "task_id": getattr(d, "task_id", task_id),
                    "diff_type": getattr(d, "diff_type", "modify"),
                    "severity": getattr(d, "severity", "medium"),
                    "similarity": getattr(d, "similarity", 0.0),
                    "text_a": getattr(d, "text_a", ""),
                    "text_b": getattr(d, "text_b", ""),
                    "position_a": getattr(d, "position_a", "{}"),
                    "position_b": getattr(d, "position_b", "{}"),
                    "chapter": getattr(d, "chapter", ""),
                })
    except Exception:
        pass

    if task_obj is None and source == "memory":
        task_obj = access_obj
        diffs = _MEMORY_DIFFS.get(task_id, [])

    if task_obj is None:
        raise HTTPException(status_code=404, detail="Task not found")

    diff_stats = {}
    try:
        stats_raw = task_obj.get("diff_stats") if isinstance(task_obj, dict) else None
        if stats_raw:
            diff_stats = json.loads(stats_raw) if isinstance(stats_raw, str) else stats_raw
    except Exception:
        diff_stats = {}

    try:
        mp_raw = task_obj.get("matched_pairs") if isinstance(task_obj, dict) else None
        if mp_raw:
            matched_pairs = json.loads(mp_raw) if isinstance(mp_raw, str) else mp_raw
    except Exception:
        matched_pairs = []

    try:
        oa_raw = task_obj.get("only_a") if isinstance(task_obj, dict) else None
        if oa_raw:
            only_a = json.loads(oa_raw) if isinstance(oa_raw, str) else oa_raw
    except Exception:
        only_a = []

    try:
        ob_raw = task_obj.get("only_b") if isinstance(task_obj, dict) else None
        if ob_raw:
            only_b = json.loads(ob_raw) if isinstance(ob_raw, str) else ob_raw
    except Exception:
        only_b = []

    # 解析 dita_full JSON
    dita_full = None
    try:
        df_raw = task_obj.get("dita_full") if isinstance(task_obj, dict) else None
        if df_raw:
            dita_full = json.loads(df_raw) if isinstance(df_raw, str) else df_raw
    except Exception:
        dita_full = None

    # 判断数据类型：通用文档有 results 字段，DITA 有 topics 字段
    is_dita_data = dita_full and isinstance(dita_full, dict) and "topics" in dita_full
    is_doc_data = dita_full and isinstance(dita_full, dict) and "results" in dita_full
    doc_full = dita_full if is_doc_data else None

    # 如果 dita_full 里存的是 doc 数据，转出来
    if is_doc_data:
        dita_full = None

    return {
        "task_id": task_obj.get("id") if isinstance(task_obj, dict) else task_id,
        "task_type": task_obj.get("task_type", "doc") if isinstance(task_obj, dict) else "doc",
        "comparison_id": task_obj.get("id") if isinstance(task_obj, dict) else task_id,
        "similarity": task_obj.get("similarity") if isinstance(task_obj, dict) else 0.0,
        "verdict": task_obj.get("verdict") if isinstance(task_obj, dict) else "",
        "total_diffs": task_obj.get("total_diffs") if isinstance(task_obj, dict) else 0,
        "diff_stats": diff_stats,
        "stats": diff_stats,
        "diffs": diffs,
        "status": task_obj.get("status") if isinstance(task_obj, dict) else "completed",
        "file_a_name": task_obj.get("file_a_name") if isinstance(task_obj, dict) else "",
        "file_b_name": task_obj.get("file_b_name") if isinstance(task_obj, dict) else "",
        "exact_match": int(task_obj.get("exact_match") or 0),
        "n_a": int(task_obj.get("n_a") or 0),
        "n_b": int(task_obj.get("n_b") or 0),
        "matched_pairs": matched_pairs,
        "only_a": only_a,
        "only_b": only_b,
        "dita_full": dita_full,
        "doc_full": doc_full,  # 通用文档数据
    }


@router.delete("/{task_id}")
async def delete_compare(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: UserOut = Depends(get_current_active_user),
):
    source, _ = _require_compare_task_access(db, task_id, current_user)
    deleted = False
    if source == "db":
        try:
            from app.crud.compare import delete_compare_task
            t = delete_compare_task(db, task_id=task_id)
            if t:
                deleted = True
        except Exception:
            pass
    if source == "memory" and task_id in _MEMORY_TASKS:
        _MEMORY_TASKS.pop(task_id, None)
        _MEMORY_DIFFS.pop(task_id, None)
        deleted = True
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"message": "Task deleted successfully", "task_id": task_id}


@router.get("/{task_id}/report")
async def generate_report(
    task_id: int,
    format: str = "html",
    db: Session = Depends(get_db),
    current_user: UserOut = Depends(get_current_active_user),
):
    data = None
    try:
        data = await read_compare(task_id, db, current_user)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=404, detail="Task not found")

    diffs = data.get("diffs", [])
    stats = data.get("diff_stats") or data.get("stats") or {}
    similarity = data.get("similarity", 0.0)
    verdict = data.get("verdict", "")
    file_a_name = data.get("file_a_name", "Document A")
    file_b_name = data.get("file_b_name", "Document B")
    total_diffs = data.get("total_diffs", 0)
    exact_match = data.get("exact_match", 0)
    n_a = data.get("n_a", 0)
    n_b = data.get("n_b", 0)
    
    matched_pairs = data.get("matched_pairs", [])
    only_a = data.get("only_a", [])
    only_b = data.get("only_b", [])
    dita_full = data.get("dita_full")
    doc_full = data.get("doc_full")

    # 判断数据类型：DITA 有 topics 字段，通用文档有 results 字段
    is_dita_data = dita_full and isinstance(dita_full, dict) and "topics" in dita_full
    is_doc_data = (dita_full and isinstance(dita_full, dict) and "results" in dita_full and "topics" not in dita_full) or (doc_full and isinstance(doc_full, dict) and "results" in doc_full)

    # 如果 dita_full 里存的是 doc 数据，转出来
    if is_doc_data and not doc_full:
        doc_full = dita_full
        dita_full = None

    # 如果 dita_full 和 doc_full 都为空，尝试从 diffs 构建 doc_full（兼容旧任务）
    if not is_dita_data and not is_doc_data and diffs:
        # 从 diffs 数据构建章节级结果
        chapters_map = {}
        for d in diffs:
            chapter = d.get("chapter", "") or "全文"
            if chapter not in chapters_map:
                chapters_map[chapter] = {
                    "heading": chapter,
                    "content_a": "",
                    "content_b": "",
                    "diffs": [],
                    "only_a": [],
                    "only_b": [],
                    "status": "部分相似",
                    "similarity": 1.0,
                }
            chapters_map[chapter]["diffs"].append({
                "a": d.get("text_a", ""),
                "b": d.get("text_b", ""),
                "score": d.get("similarity", 0.0),
                "type": d.get("diff_type", "fuzzy"),
            })
            if d.get("text_a") and not d.get("text_b"):
                chapters_map[chapter]["only_a"].append(d.get("text_a", ""))
            elif d.get("text_b") and not d.get("text_a"):
                chapters_map[chapter]["only_b"].append(d.get("text_b", ""))

        # 计算每章的相似度
        for ch_data in chapters_map.values():
            total = len(ch_data["diffs"])
            if total > 0:
                scores = [d["score"] for d in ch_data["diffs"]]
                ch_data["similarity"] = sum(scores) / total
                if ch_data["similarity"] >= 0.99:
                    ch_data["status"] = "完全一致"
                elif ch_data["similarity"] >= 0.95:
                    ch_data["status"] = "高度相似"
                elif ch_data["similarity"] >= 0.70:
                    ch_data["status"] = "部分相似"
                else:
                    ch_data["status"] = "差异较大"

        # 统计
        results = list(chapters_map.values())
        n_full = sum(1 for r in results if r["status"] == "完全一致")
        n_high = sum(1 for r in results if r["status"] == "高度相似")
        n_partial = sum(1 for r in results if r["status"] == "部分相似")
        n_low = sum(1 for r in results if r["status"] == "差异较大")
        n_only_a = sum(len(r["only_a"]) for r in results)
        n_only_b = sum(len(r["only_b"]) for r in results)

        doc_full = {
            "results": results,
            "stats": {
                "n_full": n_full,
                "n_high": n_high,
                "n_partial": n_partial,
                "n_low": n_low,
                "n_only_a": n_only_a,
                "n_only_b": n_only_b,
                "n_matched": len(results),
                "overall_sim": similarity,
            }
        }
        is_doc_data = True

    # 优先 DITA 报告
    if is_dita_data and format == "html":
        try:
            from app.utils.dita_report import render_dita_html_report
            html_content = render_dita_html_report(dita_full, file_a_name, file_b_name)
            return {"content": html_content, "format": "html"}
        except Exception as e:
            import traceback
            print(f"DITA report error: {e}")
            print(traceback.format_exc())

    # 通用文档报告（Word/PDF/MD）
    if is_doc_data and format == "html":
        try:
            from app.utils.doc_report import render_doc_html_report
            html_content = render_doc_html_report(doc_full, file_a_name, file_b_name)
            return {"content": html_content, "format": "html"}
        except Exception as e:
            import traceback
            print(f"Doc report error: {e}")
            print(traceback.format_exc())

    if format == "html":
        html_content = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>文档对比报告</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 20px; }}
.header {{ text-align: center; margin-bottom: 30px; }}
.similarity {{ font-size: 48px; color: {'#28a745' if similarity >= 0.8 else '#dc3545'}; }}
.summary {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
.summary td {{ border: 1px solid #ddd; padding: 8px; }}
.diff {{ border: 1px solid #ddd; padding: 15px; margin-bottom: 10px; }}
.add {{ background-color: #d4edda; }}
.delete {{ background-color: #f8d7da; }}
.modify {{ background-color: #fff3cd; }}
.severity-critical {{ border-left: 4px solid #dc3545; }}
.severity-high {{ border-left: 4px solid #fd7e14; }}
.severity-medium {{ border-left: 4px solid #ffc107; }}
.severity-low {{ border-left: 4px solid #28a745; }}
</style></head><body>
<div class="header"><h1>文档对比报告</h1></div>
<h2>对比概览</h2>
<p class="similarity">相似度: {similarity*100:.1f}%</p>
<p><strong>判定:</strong> {verdict}</p>
<table class="summary">
<tr><td>差异总数</td><td>{total_diffs}</td></tr>
<tr><td>新增</td><td>{stats.get('add', 0)}</td></tr>
<tr><td>删除</td><td>{stats.get('delete', 0)}</td></tr>
<tr><td>修改</td><td>{stats.get('modify', 0)}</td></tr>
</table>
<h2>详细差异</h2>
"""
        for idx, d in enumerate(diffs[:100], 1):
            dtype = d.get("diff_type", "modify")
            severity = d.get("severity", "medium")
            html_content += f"""<div class="diff {dtype} severity-{severity}">
<h3>差异 #{idx}</h3>
<p><strong>类型:</strong> {dtype}</p>
<p><strong>严重程度:</strong> {severity}</p>
<p><strong>相似度:</strong> {d.get('similarity', 0.0)*100:.1f}%</p>
<p><strong>原文:</strong> {d.get('text_a', '')}</p>
<p><strong>修改后:</strong> {d.get('text_b', '')}</p>
</div>"""
        html_content += "</body></html>"
        return {"content": html_content, "format": "html"}

    try:
        from app.utils.compare_utils import render_report
        import traceback
        report = render_report(
            file_a_name,
            file_b_name,
            "",
            "",
            {
                "similarity": similarity,
                "verdict": verdict,
                "total_diffs": total_diffs,
                "diff_stats": stats,
                "exact_match": exact_match,
                "matched_pairs": matched_pairs,
                "only_a": only_a,
                "only_b": only_b,
                "n_a": n_a,
                "n_b": n_b,
            }
        )
        return {"content": report, "format": "md"}
    except Exception as e:
        print(f"render_report error: {e}")
        print(f"Traceback: {traceback.format_exc()}")
        md_lines = [
            "# 文档对比报告",
            "",
            "## 对比概览",
            "",
            f"- 文件A: {file_a_name}",
            f"- 文件B: {file_b_name}",
            f"- 相似度: {similarity*100:.1f}%",
            f"- 判定: {verdict}",
            f"- 差异总数: {total_diffs}",
            f"- 新增: {stats.get('add', 0)}",
            f"- 删除: {stats.get('delete', 0)}",
            f"- 修改: {stats.get('modify', 0)}",
            "",
            "## 详细差异",
            "",
        ]
        for idx, d in enumerate(diffs[:100], 1):
            md_lines += [
                f"### 差异 #{idx}",
                "",
                f"- 类型: {d.get('diff_type', 'modify')}",
                f"- 严重程度: {d.get('severity', 'medium')}",
                f"- 相似度: {d.get('similarity', 0.0)*100:.1f}%",
                "",
                f"**原文:**\n{d.get('text_a', '')}",
                "",
                f"**修改后:**\n{d.get('text_b', '')}",
                "",
                "---",
                "",
            ]
        return {"content": "\n".join(md_lines), "format": "md"}


@router.get("/config")
async def get_config(db: Session = Depends(get_db)):
    try:
        from app.crud.compare import get_compare_config
        config = get_compare_config(db)
        whitelist = []
        try:
            if getattr(config, "whitelist", None):
                whitelist = json.loads(config.whitelist)
        except Exception:
            whitelist = []
        return {
            "threshold": getattr(config, "threshold", 0.8),
            "alpha": getattr(config, "alpha", 0.6),
            "beta": getattr(config, "beta", 0.4),
            "tolerance": getattr(config, "tolerance", 0.01),
            "whitelist": whitelist,
        }
    except Exception:
        return {"threshold": 0.8, "alpha": 0.6, "beta": 0.4, "tolerance": 0.01, "whitelist": []}


@router.put("/config")
async def update_config(
    threshold: float = None, alpha: float = None, beta: float = None,
    tolerance: float = None, whitelist: list = None,
    db: Session = Depends(get_db),
):
    try:
        from app.crud.compare import update_compare_config
        update_compare_config(db, threshold, alpha, beta, tolerance, whitelist)
    except Exception:
        pass
    return {"message": "Config updated successfully"}


@router.get("/{task_id}/preview/file")
async def get_preview_file(
    task_id: int,
    side: str = "a",
    db: Session = Depends(get_db),
    current_user: UserOut = Depends(get_current_active_user),
):
    """
    获取对比任务的原始预览文件
    side: 'a' 或 'b'
    """
    from fastapi.responses import FileResponse
    _require_compare_task_access(db, task_id, current_user)
    file_path, file_name = _resolve_preview_file(task_id, side)
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Preview file not found")
    media_type, _ = mimetypes.guess_type(file_name or file_path)
    return FileResponse(
        file_path,
        media_type=media_type or "application/octet-stream",
        filename=file_name or f"document_{side}",
    )


@router.get("/{task_id}/preview/content")
async def get_preview_content(
    task_id: int,
    side: str = "a",
    highlight: int = 1,
    db: Session = Depends(get_db),
    current_user: UserOut = Depends(get_current_active_user),
):
    """Return PDF metadata or HTML preview for DOCX / MD / TXT / DITA / ZIP / Excel."""
    _require_compare_task_access(db, task_id, current_user)
    file_path, file_name = _resolve_preview_file(task_id, side)
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Preview file not found")
    kind = _preview_kind(file_name or file_path)
    if kind == "pdf":
        try:
            total_pages = _pdf_page_count(file_path)
        except Exception:
            total_pages = 0
        return {
            "type": "pdf-pages",
            "file_name": file_name,
            "total_pages": total_pages,
            "content": "",
        }
    if kind == "textdiff":
        peer_side = "b" if side != "b" else "a"
        peer_path, peer_name = ("", "")
        if highlight:
            peer_path, peer_name = _resolve_preview_file(task_id, peer_side)
        return {
            "type": "textdiff",
            "file_name": file_name,
            "content": _build_compare_preview_html(
                file_path,
                file_name,
                peer_path=peer_path,
                peer_name=peer_name,
                side="b" if side == "b" else "a",
                highlight=bool(highlight),
            ),
        }
    peer_side = "b" if side != "b" else "a"
    peer_path, peer_name = ("", "")
    if highlight:
        peer_path, peer_name = _resolve_preview_file(task_id, peer_side)
    return {
        "type": "html",
        "file_name": file_name,
        "content": _build_compare_preview_html(
            file_path,
            file_name,
            peer_path=peer_path,
            peer_name=peer_name,
            side="b" if side == "b" else "a",
            highlight=bool(highlight),
        ),
    }


@router.get("/{task_id}/preview/page")
async def get_preview_page(
    task_id: int,
    side: str = "a",
    page: int = 1,
    highlight: int = 1,
    peer_page: int = 0,
    db: Session = Depends(get_db),
    current_user: UserOut = Depends(get_current_active_user),
):
    from fastapi.responses import Response
    _require_compare_task_access(db, task_id, current_user)
    file_path, file_name = _resolve_preview_file(task_id, side)
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Preview file not found")
    if _file_ext(file_name or file_path) != ".pdf":
        raise HTTPException(status_code=400, detail="Not a PDF")
    try:
        peer_side = "b" if side != "b" else "a"
        peer_path, _peer_name = _resolve_preview_file(task_id, peer_side)
        mapped = 0
        heading = ""
        if peer_path and _file_ext(peer_path) == ".pdf":
            mapped, heading = _lookup_peer_page(
                _get_preview_align(task_id).get("pairs") or [],
                page,
                "b" if side == "b" else "a",
            )
        use_highlight = bool(highlight) and bool(mapped)
        png, total = _render_pdf_page_png(
            file_path,
            page,
            peer_path=peer_path,
            peer_page=mapped,
            side="b" if side == "b" else "a",
            highlight=use_highlight,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Render failed: {e}")
    return Response(
        content=png,
        media_type="image/png",
        headers={
            "X-Total-Pages": str(total),
            "X-Peer-Page": str(mapped),
        },
    )


@router.get("/{task_id}/preview/align")
async def get_preview_align(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: UserOut = Depends(get_current_active_user),
):
    _require_compare_task_access(db, task_id, current_user)
    return _get_preview_align(task_id)


@router.get("/{task_id}/preview/info")
async def get_preview_info(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: UserOut = Depends(get_current_active_user),
):
    """
    获取预览文件信息（是否有PDF预览、文件名等）
    """
    _require_compare_task_access(db, task_id, current_user)
    info = {
        "task_id": task_id,
        "has_preview_a": False,
        "has_preview_b": False,
        "file_a_name": "",
        "file_b_name": "",
        "type_a": "",
        "type_b": "",
    }
    path_a, name_a = _resolve_preview_file(task_id, "a")
    path_b, name_b = _resolve_preview_file(task_id, "b")
    if name_a:
        info["file_a_name"] = name_a
    if name_b:
        info["file_b_name"] = name_b
    info["has_preview_a"] = bool(path_a)
    info["has_preview_b"] = bool(path_b)
    info["type_a"] = _preview_kind(name_a or path_a) if path_a else ""
    info["type_b"] = _preview_kind(name_b or path_b) if path_b else ""
    return info


@router.get("/{task_id}/preview/textdiff")
async def get_preview_textdiff(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: UserOut = Depends(get_current_active_user),
):
    """Line-aligned text diff for Markdown / TXT, Beyond Compare layout."""
    _require_compare_task_access(db, task_id, current_user)
    path_a, name_a = _resolve_preview_file(task_id, "a")
    path_b, name_b = _resolve_preview_file(task_id, "b")
    if not path_a or not os.path.exists(path_a) or not path_b or not os.path.exists(path_b):
        raise HTTPException(status_code=404, detail="Preview file not found")
    from app.utils.md_compare import build_aligned_text_diff
    text_a = _read_text_preview(path_a, limit=800000)
    text_b = _read_text_preview(path_b, limit=800000)
    data = build_aligned_text_diff(text_a, text_b)
    data["file_a_name"] = name_a
    data["file_b_name"] = name_b
    return data
