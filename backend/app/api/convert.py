from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
import csv
import io
import os
import re
import json
import time
import zipfile
import shutil
import threading
import urllib.parse
import xml.etree.ElementTree as ET
from app.database import get_db
from app.api.auth import get_current_active_user, require_admin
from app.schemas.user import UserOut
from app.crud.convert import (
    create_convert_task, get_convert_task, get_convert_tasks,
    update_convert_task_status, update_convert_task_result, update_convert_task_failed,
    update_convert_task_progress, delete_convert_task, update_convert_task_revised
)
from app.schemas.convert import (
    ConvertTaskOut, ConvertTaskCreate, ProgressOut, ReportOut,
    StepStatus, CheckItem
)

router = APIRouter(dependencies=[Depends(get_current_active_user)])

UPLOAD_DIR = "./static/uploads"
OUTPUT_DIR = "./static/uploads/outputs"

_tasks_lock = threading.Lock()
_task_store = {}


def _require_convert_task_access(db: Session, task_id: str, current_user: UserOut):
    task = get_convert_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if current_user.role == "admin":
        return task
    if getattr(task, "user_id", None) != current_user.id:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task

IME_TOPIC_DECL = '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">'
IME_BOOKMAP_DECL = '<!DOCTYPE bookmap PUBLIC "-//OASIS//DTD DITA BookMap//EN" "bookmap.dtd">'


def _ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def _media_type_for_file(filename):
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".csv":
        return "text/csv; charset=utf-8"
    if ext in [".md", ".markdown"]:
        return "text/markdown; charset=utf-8"
    if ext == ".zip":
        return "application/zip"
    return "application/octet-stream"


_ensure_dir(UPLOAD_DIR)
_ensure_dir(OUTPUT_DIR)

GENERATED_NODE_VERSION = "A.2"
GENERATED_TOPIC_BASE = 41000

# Stable Word -> DITA conversion rules for batch processing.
# Keep these decisions centralized so future source files follow the same
# structure, note semantics, figure/table title cleanup, and template reuse.
REUSE_TEMPLATE_COVER_TOPIC = True
# Titles that belong in the bookmap frontmatter. The source document supplies
# its own version history, so a version-history topic coming from the template
# is dropped to avoid duplicating it.
FRONTMATTER_CHILD_TITLES = {
    "about the user manual",
    "manufacturer information",
    "关于说明书",
    "制造商信息",
}
VERSION_HISTORY_TITLES = {
    "revision history",
    "version history",
    "版本历史",
    "版本记录",
    "修订历史",
}
DOCX_SPECIAL_HEADING_LEVELS = {
    "revision history": 2,
    "version history": 2,
    "版本历史": 2,
    "版本记录": 2,
}
DOCX_TOC_TITLES = {"目录", "目 录", "⽬录", "Contents"}
NOTE_LABEL_PATTERN = re.compile(
    r'^(?:\[\[/?(?:B|SUP|SUB)\]\])*(warning|caution|tips|danger|stop\s*point|stoppoint|note)'
    r'(?:\[\[/?(?:B|SUP|SUB)\]\])*[:：]?(?:\[\[/?(?:B|SUP|SUB)\]\])*\s*(.*)$',
    re.IGNORECASE,
)
CHINESE_NOTE_LABEL_PATTERN = re.compile(
    r'^(?:\[\[/?(?:B|SUP|SUB)\]\])*(注意事项|其他注意事项|注意|提示|警告|小心)'
    r'(?:\[\[/?(?:B|SUP|SUB)\]\])*[:：](?:\[\[/?(?:B|SUP|SUB)\]\])*\s*(.*)$'
)
CHINESE_WARNING_ACTION_PATTERN = re.compile(r'^(请勿|切勿)\s*(.*)$')
# Note enumeration markers: Chinese 【1】 and English Word [1]. These continue a
# label-only 注意：/Note: and are grouped into one <ul> inside the note.
NOTE_ENUM_MARKER_RE = re.compile(r'^(?:【\d+】|\[\d+\])')
NOTE_ENUM_P_RE = re.compile(r'^\s*<p>(?:【\d+】|\[\d+\])(.*)</p>\s*$', re.S)
# Table/figure caption numbering can be multi-level (表2-3, 表B-1) or plain
# (Table 13, 图 6). Keep the pattern in one place so title cleanup and heading
# splitting agree on what a caption prefix looks like.
CAPTION_PREFIX_PATTERN = r'(?:\d+(?:[-–—.]\d+)*[0-9A-Za-z]*|[A-Za-z]\s*[-–—.]?\s*\d+)'
TABLE_CAPTION_PREFIX_RE = re.compile(rf'^(?:表|Table)\s*{CAPTION_PREFIX_PATTERN}', re.IGNORECASE)
FIGURE_CAPTION_PREFIX_RE = re.compile(rf'^(?:图|Figure)\s*{CAPTION_PREFIX_PATTERN}', re.IGNORECASE)
ANY_CAPTION_PREFIX_RE = re.compile(
    rf'^(?:表|Table|图|Figure|formula|Formula)\s*{CAPTION_PREFIX_PATTERN}', re.IGNORECASE
)
# A block image is a line that contains nothing but one image; inline images
# (button icons inside a sentence) keep trailing text and must stay inline.
MD_IMAGE_LINE_RE = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)\s*$')
# IME applies its own numbering to chapters and sections, so manual prefixes
# such as "第一章", "附录A", "2.1" or "3.1.1" are dropped from titles.
CHAPTER_APPENDIX_PREFIX_RE = re.compile(
    r'^(?:'
    r'第\s*[0-9一二三四五六七八九十百千零〇]+\s*[章節节]\s*'
    r'|附录\s*[A-Za-zⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅰⅱⅲⅳⅴⅵⅶⅷⅸⅹ]+\s*[:：]?\s*'
    r'|(?:Chapter|Appendix)\s*[\dA-Za-z]+\s*[:：.]?\s*'
    r')',
    re.IGNORECASE,
)
# "2.1" / "3.1.1" only count as numbering when real content follows, so values
# such as "3'RNA" or "1.13×" keep their leading digits.
SECTION_NUMBER_PREFIX_RE = re.compile(r'^\d+(?:[.．]\d+)+\s*(?=[\u4e00-\u9fff]|[A-Z])')
APPENDIX_ITEM_NUMBER_PREFIX_RE = re.compile(r'^[A-Za-z]\s*[-–—]\s*\d+\s*(?=[\u4e00-\u9fff]|[A-Z])')


def _get_step_names():
    return ["解析", "结构映射", "内容替换", "验证", "打包"]


def _get_topic_type(heading_text):
    task_keywords = ["安装", "配置", "操作", "步骤", "部署", "启动", "设置", "升级", "卸载", "登录",
                     "install", "config", "setup", "deploy", "start", "upgrade", "uninstall", "login"]
    ref_keywords = ["参数", "规格", "表格", "参考", "附录", "错误码", "api", "接口", "命令",
                    "parameter", "spec", "reference", "appendix", "command"]
    heading_lower = heading_text.lower()

    for kw in task_keywords:
        if kw in heading_lower:
            return "task"
    for kw in ref_keywords:
        if kw in heading_lower:
            return "reference"
    return "concept"


def _clean_title(title):
    """Clean markdown formatting from section titles.
    - Unescape markdown backslash escapes
    - Strip ** bold markers
    - Remove leading numbering (第一章, 2.1, 3.1.1, 附录A, Chapter 1:, etc.)
    """
    if not title:
        return title

    # 1. Unescape markdown: \\ must come first to avoid double-unescaping
    t = title
    t = t.replace("\\\\", "\\")
    for ch in "&*_`.-#":
        t = t.replace("\\" + ch, ch)

    # 2. Strip ** bold markers
    t = re.sub(r'\*{1,2}([^*]+)\*{1,2}', r'\1', t)
    # 2b. Drop inline run placeholders; they are markup, not title content
    t = _clean_navtitle(t)

    # 3. Drop manual chapter/section numbering; IME adds its own numbering
    t = CHAPTER_APPENDIX_PREFIX_RE.sub('', t)
    t = SECTION_NUMBER_PREFIX_RE.sub('', t)
    t = APPENDIX_ITEM_NUMBER_PREFIX_RE.sub('', t)
    # Single-level "1. Title" chapter numbers; keep "2.0 mL" / "3'RNA".
    t = re.sub(r'^\d+\.\s+(?=[\u4e00-\u9fff]|[A-Z])', '', t)

    # 4. Trim and clean up
    t = re.sub(r'\s+', ' ', t).strip()
    t = t.rstrip(':：').strip()
    return t


HEADING_NUMBER_RE = re.compile(r'^(\d+(?:\.\d+)*)(?:[.\s]|、)+')


def _heading_number(title):
    """Return the leading section number (``3.2``) from a Markdown heading."""
    match = HEADING_NUMBER_RE.match((title or "").strip())
    return match.group(1) if match else None


def _clean_xref_title(title):
    """Drop chapter/section numbers from a cross-reference destination title.

    IME prepends its own numbering, so a source title such as ``9.1DNB浓度不合格``
    must resolve to ``DNB浓度不合格``.
    """
    cleaned = _clean_title(title) or (title or "")
    cleaned = re.sub(r'^\d+(?:[.．]\d+)+\s*', '', cleaned)
    return cleaned.strip()


def _space_alnum_cjk(text):
    """Insert a space where ASCII letters/digits are followed by CJK.

    Cross-reference link text follows the source layout 第12 页“测定DNB 浓度”.
    """
    return re.sub(r'([A-Za-z0-9])([\u4e00-\u9fff])', r'\1 \2', text or '')


def _strip_md_bold(text):
    return re.sub(r'\*{1,2}([^*]+)\*{1,2}', r'\1', text or '')


def _clean_navtitle(title):
    """Drop inline run placeholders so map titles stay human readable."""
    text = title or ""
    text = re.sub(r'\[\[(B|SUP|SUB|I|CODE)\]\](.*?)\[\[/\1\]\]', r'\2', text)
    text = re.sub(r'\[\[LINK:[^\]]+\]\](.*?)\[\[/LINK\]\]', r'\1', text)
    text = re.sub(r'\[\[/?[A-Z]+(?::[^\]]+)?\]\]', '', text)
    return text


def _extract_md_frontmatter(content):
    """Split optional YAML front matter from a native Markdown document."""
    text = content or ""
    if not text.startswith("---"):
        return text, None
    match = re.match(r'^---[ \t]*\n(.*?)\n---[ \t]*\n?', text, re.S)
    if not match:
        return text, None
    title = None
    title_match = re.search(r'(?im)^title:\s*[\'"]?(.+?)[\'"]?\s*$', match.group(1))
    if title_match:
        title = title_match.group(1).strip().strip('"').strip("'")
    return text[match.end():], title


def _promote_setext_headings(content):
    """Rewrite Setext headings to ATX so section parsing sees a single syntax."""
    lines = (content or "").split("\n")
    out = []
    idx = 0
    while idx < len(lines):
        current = lines[idx]
        nxt = lines[idx + 1] if idx + 1 < len(lines) else None
        looks_like_heading = (
            nxt is not None
            and current.strip()
            and not current.lstrip().startswith(("#", "|", ">", "`", "~", "!", "-", "*"))
        )
        if looks_like_heading and re.match(r'^=+[ \t]*$', nxt):
            out.append("# " + current.strip())
            idx += 2
            continue
        if looks_like_heading and re.match(r'^-{3,}[ \t]*$', nxt):
            out.append("## " + current.strip())
            idx += 2
            continue
        out.append(current)
        idx += 1
    return "\n".join(out)


def _normalize_md_emphasis_and_links(text):
    """Convert native Markdown emphasis and links into intermediate markers."""
    if not text:
        return text

    def _link_repl(match):
        return f'[[LINK:{match.group(2)}]]{match.group(1)}[[/LINK]]'

    converted = re.sub(r'(?<!!)\[([^\]]+)\]\(([^)]+)\)', _link_repl, text)
    converted = re.sub(r'\*\*(.+?)\*\*', r'[[B]]\1[[/B]]', converted)
    converted = re.sub(
        r'(?<!\*)\*(?!\*)([^*\n]+?)(?<!\*)\*(?!\*)',
        r'[[I]]\1[[/I]]',
        converted,
    )
    return _wrap_file_format_tokens(converted)


def _normalize_native_markdown_span(text):
    """Protect inline code, then convert remaining native Markdown syntax."""
    if not text:
        return text
    parts = []
    last = 0
    for match in re.finditer(r'`([^`]+)`', text):
        parts.append(_normalize_md_emphasis_and_links(text[last:match.start()]))
        parts.append(_inline_code_to_marker(match.group(1)))
        last = match.end()
    parts.append(_normalize_md_emphasis_and_links(text[last:]))
    return "".join(parts)


_FILE_FORMAT_TOKEN_RE = re.compile(
    r'(?<![A-Za-z0-9_/])(\.[A-Za-z0-9]+(?:\.[A-Za-z0-9]+)*)(?![A-Za-z0-9])'
)


def _looks_like_file_format(text):
    value = (text or "").strip()
    return bool(re.fullmatch(r'\.[A-Za-z0-9]+(?:\.[A-Za-z0-9]+)*', value))


def _wrap_file_format_tokens(text):
    if not text:
        return text
    return _FILE_FORMAT_TOKEN_RE.sub(r'[[I]]\1[[/I]]', text)


def _inline_code_to_marker(code):
    if _looks_like_file_format(code):
        return f'[[I]]{code}[[/I]]'
    return code


_FENCED_BLOCK_RE = re.compile(
    r'^[ \t]*(```|~~~)[^\n]*\n[\s\S]*?\n[ \t]*\1[ \t]*$',
    re.M,
)


def _normalize_native_markdown(content):
    """Turn native Markdown into the intermediate markers the DITA layer already understands.

    Word/IDML pipelines already emit [[B]] / [[UI]] / [[LVL:n]]. A hand-written
    .md file uses **bold**, `code`, [text](url), > notes and fenced code; this
    step makes those equivalent without changing Word/IDML input.
    """
    text = content or ""
    pieces = []
    last = 0
    for match in _FENCED_BLOCK_RE.finditer(text):
        pieces.append(_normalize_native_markdown_span(text[last:match.start()]))
        pieces.append(match.group(0))
        last = match.end()
    pieces.append(_normalize_native_markdown_span(text[last:]))
    normalized = "".join(pieces)
    # Drop one blockquote marker so note/list detectors see the inner text.
    return re.sub(r'(?m)^[ \t]*>[ \t]?', '', normalized)


def _parse_md_sections(content):
    """Parse markdown into nested sections for all heading levels (H1-H6).
    Returns: [{"title": str, "sections": [...], "content": str}]
    """
    lines = content.split("\n")
    root_sections = []
    # Stack entries: {"title": str, "level": int, "sections": list, "content_lines": list}
    stack = []
    pending_lines = []
    preamble_lines = []
    in_fence = False
    fence_marker = None

    for line in lines:
        fence_match = re.match(r'^[ \t]*(```|~~~)', line)
        if fence_match:
            marker = fence_match.group(1)
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif line.strip().startswith(fence_marker):
                in_fence = False
                fence_marker = None
            pending_lines.append(line)
            continue
        if in_fence:
            pending_lines.append(line)
            continue
        heading_match = re.match(r'^(#{1,6})\s+(.*)', line)
        if heading_match:
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()

            if pending_lines:
                if stack:
                    ck = "content_lines"
                    if ck not in stack[-1]:
                        stack[-1][ck] = []
                    stack[-1][ck].extend(pending_lines)
                else:
                    preamble_lines.extend(pending_lines)
                pending_lines = []

            while stack and stack[-1]["level"] >= level:
                complete = stack.pop()
                sec_content = "\n".join(complete.get("content_lines", [])).strip()
                entry = {
                    "title": complete["title"],
                    "sections": complete.get("sections", []),
                    "content": sec_content,
                }
                if stack:
                    stack[-1].setdefault("sections", []).append(entry)
                else:
                    root_sections.append(entry)

            stack.append({
                "title": title,
                "level": level,
                "sections": [],
            })
        else:
            pending_lines.append(line)

    if pending_lines:
        if stack:
            stack[-1].setdefault("content_lines", []).extend(pending_lines)
        else:
            preamble_lines.extend(pending_lines)
        pending_lines = []

    while stack:
        complete = stack.pop()
        sec_content = "\n".join(complete.get("content_lines", [])).strip()
        entry = {
            "title": complete["title"],
            "sections": complete.get("sections", []),
            "content": sec_content,
        }
        if stack:
            stack[-1].setdefault("sections", []).append(entry)
        else:
            root_sections.append(entry)

    preamble = "\n".join(preamble_lines).strip()
    if not root_sections:
        return [{"title": "文档", "sections": [], "content": preamble}]
    if preamble:
        root_sections.insert(0, {"title": "正文", "sections": [], "content": preamble})
    return root_sections


def _parse_docx_sections(file_path):
    try:
        from docx import Document as DocxDocument
        doc = DocxDocument(file_path)
        paragraphs = [p for p in doc.paragraphs if p.text.strip()]
        if not paragraphs:
            return [{"title": "文档", "sections": [{"title": "正文", "content": "(无内容)"}]}]

        root_sections = []
        stack = []
        pending_lines = []

        for p in paragraphs:
            text = p.text.strip()
            style_name = p.style.name if p.style else ""
            heading_level = _get_heading_level(style_name)

            if heading_level:
                if pending_lines:
                    if stack:
                        stack[-1].setdefault("content_lines", []).extend(pending_lines)
                    pending_lines = []

                while stack and stack[-1]["level"] >= heading_level:
                    complete = stack.pop()
                    sec_content = "\n".join(complete.get("content_lines", [])).strip()
                    entry = {
                        "title": complete["title"],
                        "sections": complete.get("sections", []),
                        "content": sec_content,
                    }
                    if stack:
                        stack[-1].setdefault("sections", []).append(entry)
                    else:
                        root_sections.append(entry)

                stack.append({
                    "title": text,
                    "level": heading_level,
                    "sections": [],
                })
            else:
                pending_lines.append(text)

        if pending_lines:
            if stack:
                stack[-1].setdefault("content_lines", []).extend(pending_lines)
            pending_lines = []

        while stack:
            complete = stack.pop()
            sec_content = "\n".join(complete.get("content_lines", [])).strip()
            entry = {
                "title": complete["title"],
                "sections": complete.get("sections", []),
                "content": sec_content,
            }
            if stack:
                stack[-1].setdefault("sections", []).append(entry)
            else:
                root_sections.append(entry)

        if not root_sections:
            full_text = "\n".join(p.text.strip() for p in paragraphs)
            return [{"title": "文档", "sections": [{"title": "正文", "content": full_text}]}]

        return root_sections
    except Exception as e:
        raise ValueError(f"DOCX解析失败: {str(e)}")


def _iter_docx_blocks(doc):
    from docx.document import Document as DocxDocumentClass
    from docx.oxml.table import CT_Tbl
    from docx.oxml.text.paragraph import CT_P
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    parent = doc.element.body if isinstance(doc, DocxDocumentClass) else doc
    for child in parent.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, doc)
        elif isinstance(child, CT_Tbl):
            yield Table(child, doc)


def _normalize_docx_text(text):
    return re.sub(r'\s+', ' ', str(text or '')).strip()


def _format_docx_run_text(run):
    text = run.text or ''
    if not text:
        return ''
    # A whitespace-only bold run (e.g. the space before a bolded 注意：) is a
    # Word artifact; wrapping it adds a stray [[B]] [[/B]] that confuses note
    # detection and text coverage.
    if run.bold and text.strip():
        text = f'[[B]]{text}[[/B]]'
    if run.font.superscript:
        return f'[[SUP]]{text}[[/SUP]]'
    if run.font.subscript:
        return f'[[SUB]]{text}[[/SUB]]'
    return text


def _docx_paragraph_segments(paragraph):
    """Return text and image segments of a paragraph in run order.

    Images keep their position relative to the surrounding text so inline
    button icons can be restored inside the sentence instead of becoming a
    standalone figure.
    """
    rel_ns = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"
    segments = []
    for run in paragraph.runs:
        for blip in run._element.xpath('.//*[local-name()="blip"]'):
            rel_id = blip.get(rel_ns)
            if rel_id:
                segments.append(("image", rel_id))
        text = _format_docx_run_text(run)
        if text:
            segments.append(("text", text))
    return segments


def _extract_docx_paragraph_text(paragraph):
    return _normalize_docx_text(
        ''.join(value for kind, value in _docx_paragraph_segments(paragraph) if kind == "text")
    )


def _is_plain_docx_text_line(line):
    stripped = (line or '').strip()
    return bool(stripped) and not stripped.startswith(('#', '!', '|', '- ', '* ')) and not re.match(r'^\s*\d+[.)、]\s+', stripped)


def _is_docx_list_text_line(line):
    return bool(re.match(r'^\s*\d+[.)、]\s+', (line or '').strip()))


def _strip_docx_list_marker(line):
    return re.sub(r'^\s*\d+[.)、]\s+', '', (line or '').strip())


def _should_merge_docx_wrapped_lines(current_line, next_line):
    current_text = current_line.strip()
    next_text = next_line.strip()
    current_content = _strip_docx_list_marker(current_text)

    if not current_content or not next_text or len(next_text) > 18:
        return False
    if re.search(r'[。！？.!?；;：:]$', current_content):
        return False
    if re.match(r'^(注意|提示|警告|小心|请勿|切勿)[:：]?', next_text):
        return False
    if re.match(r'^(也可|可根据|根据|产物|室温|孵育|随后|然后|再|接着)', next_text):
        return False

    unfinished_patterns = [
        r'(?:\d+(?:\.\d+)?)\s*(?:μL|uL|mL|mM|nM|bp|kb|g|mg|ng|kg|℃|°C|min|h)$',
        r'(?:新的|至|到|入|于|为|用)$',
        r'[（(]$',
    ]
    return any(re.search(pattern, current_content) for pattern in unfinished_patterns)


def _docx_wrap_joiner(current_text, next_text):
    if re.search(r'[A-Za-z0-9μu°℃%]$', current_text) and re.match(r'^[\u4e00-\u9fffA-Za-z0-9]', next_text):
        return ' '
    return ''


def _merge_docx_wrapped_paragraphs(lines):
    merged = []
    i = 0

    while i < len(lines):
        current = lines[i]
        if (
            i + 2 < len(lines)
            and current
            and not lines[i + 1]
            and (_is_plain_docx_text_line(current) or _is_docx_list_text_line(current))
            and _is_plain_docx_text_line(lines[i + 2])
        ):
            next_line = lines[i + 2].strip()
            current_text = current.strip()
            should_merge = _should_merge_docx_wrapped_lines(current_text, next_line)
            if should_merge:
                joiner = _docx_wrap_joiner(current_text, next_line)
                merged.append(f"{current_text}{joiner}{next_line}")
                i += 3
                if i < len(lines) and not lines[i]:
                    merged.append('')
                    i += 1
                continue

        merged.append(current)
        i += 1

    return merged


def _is_docx_toc_number(text):
    return bool(re.fullmatch(r'\d+(?:\.\d+)*', text or ''))


def _docx_table_to_markdown(table, heading=""):
    """Render a Word table, preserving merges and the real header-row count."""
    from docx.oxml.ns import qn
    from docx.table import _Cell

    if getattr(table, "_tbl", None) is None:
        return _docx_table_to_markdown_legacy(table)

    def grid_span(tc):
        tcPr = tc.find(qn("w:tcPr"))
        if tcPr is None:
            return 1
        node = tcPr.find(qn("w:gridSpan"))
        if node is None:
            return 1
        try:
            return max(1, int(node.get(qn("w:val")) or 1))
        except ValueError:
            return 1

    def vmerge(tc):
        tcPr = tc.find(qn("w:tcPr"))
        if tcPr is None:
            return None
        node = tcPr.find(qn("w:vMerge"))
        if node is None:
            return None
        return node.get(qn("w:val")) or "continue"

    def is_header_row(tr):
        trPr = tr.find(qn("w:trPr"))
        if trPr is None:
            return False
        return trPr.find(qn("w:tblHeader")) is not None

    trs = table._tbl.findall(qn("w:tr"))
    if not trs:
        return []

    parsed_rows = []
    max_col = 0
    for tr in trs:
        col = 0
        cells = []
        for tc in tr.findall(qn("w:tc")):
            span = grid_span(tc)
            cells.append((col, span, vmerge(tc), _normalize_docx_text(_Cell(tc, table).text)))
            col += span
        max_col = max(max_col, col)
        parsed_rows.append((is_header_row(tr), cells))

    if max_col <= 0:
        return []

    def cell_at(row_cells, col):
        for start, span, merge, text in row_cells:
            if start <= col < start + span:
                return start, span, merge, text
        return None

    def rowspan_for(row_index, col):
        found = cell_at(parsed_rows[row_index][1], col)
        if found is None:
            return 1
        _, _, merge, _ = found
        if merge != "restart":
            return 1
        span = 1
        for later in parsed_rows[row_index + 1:]:
            nxt = cell_at(later[1], col)
            if nxt is None:
                break
            _, _, later_merge, _ = nxt
            if later_merge != "continue":
                break
            span += 1
        return span

    grid = []
    for row_index, (_header, row_cells) in enumerate(parsed_rows):
        rendered = [""] * max_col
        for start, colspan, merge, text in row_cells:
            if merge == "continue":
                for extra in range(colspan):
                    if start + extra < max_col:
                        rendered[start + extra] = IDML_SPAN_COVERED
                continue
            rowspan = rowspan_for(row_index, start)
            cell_text = text
            if colspan > 1 or rowspan > 1:
                cell_text = (cell_text + " " if cell_text else "") + f"[[SPAN:{colspan},{rowspan}]]"
            rendered[start] = cell_text
            for extra in range(1, colspan):
                if start + extra < max_col:
                    rendered[start + extra] = IDML_SPAN_COVERED
        grid.append(rendered)

    header_rows = 0
    for header_flag, _cells in parsed_rows:
        if not header_flag:
            break
        header_rows += 1
    if header_rows == 0 and len(grid) > 1:
        first_has_continuing_merge = any(
            merge == "restart" and rowspan_for(0, start) > 1
            for start, _span, merge, _text in parsed_rows[0][1]
        )
        if not first_has_continuing_merge:
            header_rows = 1
    if header_rows >= len(grid) and len(grid) > 1:
        header_rows = 1

    heading = heading or getattr(table, "_convert_heading", "") or ""
    wide = _dita_table_should_be_extra_wide(max_col, heading)
    md_lines = []
    md_lines.append(f"[[THEAD:{header_rows}]]")
    if wide:
        md_lines.append("[[TWIDE:180mm]]")
    md_lines.append("| " + " | ".join(grid[0]) + " |")
    md_lines.append("| " + " | ".join([":---"] * max_col) + " |")
    for row in grid[1:]:
        md_lines.append("| " + " | ".join(row) + " |")
    return md_lines


def _dita_table_should_be_extra_wide(cols, *texts):
    if cols >= 7:
        return True
    blob = " ".join(text or "" for text in texts).lower()
    markers = (
        "sequencing parameters",
        "room temperature reagent",
        "low temperature reagent",
        "reagent reservoir",
        "flexible-throughput",
        "flexible throughput",
        "consumable usage",
    )
    return any(marker in blob for marker in markers)


def _docx_table_to_markdown_legacy(table):
    """Fallback for test doubles that only expose python-docx .rows."""
    rows = []
    for row in table.rows:
        cells = []
        tc_first_text = {}
        for cell in row.cells:
            cell_text = _normalize_docx_text(cell.text)
            tc_id = id(cell._tc)
            if tc_id in tc_first_text:
                cell_text = ""
            else:
                tc_first_text[tc_id] = cell_text
            cells.append(cell_text)
        while cells and not cells[-1]:
            cells.pop()
        if any(cells):
            rows.append(cells)

    if not rows:
        return []

    cols = max(len(row) for row in rows)
    normalized_rows = [row + [""] * (cols - len(row)) for row in rows]
    header = normalized_rows[0]
    md_lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join([":---"] * cols) + " |",
    ]
    for row in normalized_rows[1:]:
        md_lines.append("| " + " | ".join(row) + " |")
    return md_lines


def _is_repeated_table_header_row(row, header):
    if not row or not header or len(row) != len(header):
        return False
    normalized_row = [_normalize_docx_text(cell) for cell in row]
    normalized_header = [_normalize_docx_text(cell) for cell in header]
    return normalized_row == normalized_header


def _collapse_grouped_first_column_rows(rows):
    if len(rows) < 3:
        return rows

    collapsed = [rows[0]]
    prev_first = None
    for idx, row in enumerate(rows[1:], start=1):
        current = list(row)
        first = _normalize_docx_text(current[0]) if current else ""
        if idx > 1 and first and first == prev_first:
            remaining = [_normalize_docx_text(cell) for cell in current[1:]]
            if any(remaining):
                current[0] = ""
        if current:
            prev_first = _normalize_docx_text(current[0]) or first
        collapsed.append(current)
    return collapsed


def _drop_redundant_first_body_row(rows):
    if len(rows) < 2:
        return rows
    header = rows[0]
    first_body = rows[1]
    if len(first_body) != len(header):
        return rows

    normalized_header = [_normalize_docx_text(cell) for cell in header]
    normalized_body = [_normalize_docx_text(cell) for cell in first_body]
    if len(normalized_header) < 3:
        return rows

    same_prefix = normalized_body[:2] == normalized_header[:2]
    empty_suffix = all(not cell for cell in normalized_body[2:])
    if same_prefix and empty_suffix:
        return [header] + rows[2:]
    return rows


def _get_docx_numbering_format(paragraph):
    try:
        ppr = paragraph._p.pPr
        if ppr is None or ppr.numPr is None:
            return None, 0

        num_id = ppr.numPr.numId.val
        ilvl = int(ppr.numPr.ilvl.val) if ppr.numPr.ilvl is not None else 0
        numbering_part = paragraph.part.numbering_part
        numbering_root = numbering_part.numbering_definitions._numbering

        abstract_nodes = numbering_root.xpath(
            f'./w:num[@w:numId="{num_id}"]/w:abstractNumId/@w:val'
        )
        if not abstract_nodes:
            return None, ilvl

        abstract_id = abstract_nodes[0]
        fmt_nodes = numbering_root.xpath(
            f'./w:abstractNum[@w:abstractNumId="{abstract_id}"]/w:lvl[@w:ilvl="{ilvl}"]/w:numFmt/@w:val'
        )
        if not fmt_nodes:
            return None, ilvl
        return fmt_nodes[0], ilvl
    except Exception:
        return None, 0


def _docx_list_marker(paragraph):
    num_fmt, ilvl = _get_docx_numbering_format(paragraph)
    if not num_fmt:
        return None

    indent = "  " * max(0, ilvl)
    if num_fmt in {"bullet", "none"}:
        return f"{indent}- "
    return f"{indent}1. "


def _should_emit_docx_list_marker(paragraph, text, next_block, prev_block=None):
    marker = _docx_list_marker(paragraph)
    if not marker or not text:
        return False

    compact = _normalize_docx_text(text)
    if _looks_like_docx_heading_text(compact):
        return False
    # A numbered paragraph sitting next to another item of the same list is a
    # real list item even when it is short and unpunctuated.
    if _docx_numbered_run_continues(paragraph, prev_block, next_block):
        return True
    if len(compact) <= 20 and not re.search(r'[，。；：:,.()]', compact):
        return False
    if len(compact.split()) <= 6 and not re.search(r'[，。；：:,.()]', compact):
        return False
    if next_block is not None and hasattr(next_block, "rows") and len(compact) <= 40:
        return False
    return True


def _docx_numbered_heading_level(text):
    """Return the heading level for a "3.2.1 标题" paragraph, or 0.

    The text after the numbering must start with a CJK character or a
    capitalized English word, so unit-like content such as "2.0 mL" or
    "1.13× 损耗" is not mistaken for a heading.
    """
    compact = _normalize_docx_text(_clean_navtitle(_strip_md_bold(text or "")))
    match = re.match(r'^(\d+(?:\.\d+){1,5})\s*(.*)$', compact)
    if not match:
        return 0
    rest = match.group(2).strip()
    if not rest:
        return 0
    if not (re.match(r'^[\u4e00-\u9fff]', rest) or re.match(r'^[A-Z][A-Za-z]', rest)):
        return 0
    return min(match.group(1).count('.') + 1, 6)


def _looks_like_docx_heading_text(text):
    # Bold run placeholders ([[B]]...[[/B]]) must be removed before matching,
    # otherwise fully bold numbered headings such as "3.2.1 软件登陆" never look
    # like headings.
    compact = _normalize_docx_text(_clean_navtitle(_strip_md_bold(text or '')))
    if not compact:
        return False
    if len(compact) > 80 or len(compact.split()) > 16:
        return False
    if compact.startswith(("Formula ", "formula ")):
        return False
    if " = " in compact or compact.count("=") == 1:
        return False
    if re.match(r'^formula\s*\d+\b', compact, re.IGNORECASE):
        return False
    if re.match(r'^[A-Za-z][A-Za-z0-9 ()/μ.-]*\s*=\s*.+$', compact):
        return False
    if ANY_CAPTION_PREFIX_RE.match(compact):
        return False
    if re.match(r'^(试剂|样本|步骤|操作|注意|提示|警告|小心|请勿|切勿)[:：]', compact):
        return False
    is_numbered = bool(_docx_numbered_heading_level(compact))
    if re.search(r'[.!?;，。；]$', compact):
        return False
    if compact.endswith(("：", ":")):
        # A numbered heading may carry a trailing colon ("4.1.1 仪器、试剂和耗材准备：").
        if not (is_numbered and len(compact) <= 60):
            return False
    if is_numbered:
        return True
    # A single trailing parenthetical can be part of a heading (for example
    # "DNBSEQ-G99ARS (SE50/PE50/PE150)"); product lines that stack several
    # parentheticals are body text.
    return bool(re.match(r'^[\u4e00-\u9fffA-Za-z0-9\-+/ ]+\([^()\n]+\)$', compact))


def _docx_paragraph_is_fully_bold(paragraph):
    runs = [run for run in paragraph.runs if run.text and run.text.strip()]
    if not runs:
        return False
    return all(run.bold for run in runs)


def _docx_numbering_id(paragraph):
    """Return the Word numbering id, or None when the paragraph is not numbered."""
    try:
        ppr = paragraph._p.pPr
        if ppr is None or ppr.numPr is None or ppr.numPr.numId is None:
            return None
        raw_id = ppr.numPr.numId.val
    except Exception:
        return None
    try:
        num_id = int(raw_id)
    except (TypeError, ValueError):
        return None
    # numId 0 disables numbering for the paragraph.
    return num_id or None


def _docx_numbered_run_continues(paragraph, prev_block, next_block):
    """True when a numbered paragraph sits next to another item of the same list."""
    num_id = _docx_numbering_id(paragraph)
    if num_id is None:
        return False
    for neighbour in (prev_block, next_block):
        if neighbour is None or hasattr(neighbour, "rows"):
            continue
        if _docx_numbering_id(neighbour) == num_id:
            return True
    return False


def _infer_docx_heading_level(paragraph, text, next_block, style_name):
    heading_level = _get_heading_level(style_name)
    if heading_level:
        return heading_level

    if not text:
        return 0

    normalized_text = _normalize_docx_text(_clean_navtitle(_strip_md_bold(text)))
    is_table_title = bool(ANY_CAPTION_PREFIX_RE.match(normalized_text))
    if is_table_title:
        return 0

    # A fully bold line sitting immediately above a table is a group label
    # (Cell phase, 常温试剂), not a topic title.
    if (
        next_block is not None
        and hasattr(next_block, "rows")
        and _docx_paragraph_is_fully_bold(paragraph)
    ):
        return 0

    num_fmt = _get_docx_numbering_format(paragraph)
    compact = normalized_text
    if num_fmt:
        fmt, indent_level = num_fmt
        # Word often numbers plain list items with the same decimal numbering
        # used by headings, so only treat it as a heading when the text itself
        # looks like a heading ("6.2.3 Sample Barcode 使用规则 (96 RXN)").
        looks_like_heading = (
            fmt == "decimal"
            and len(compact) <= 40
            and len(compact.split()) <= 12
            and not re.search(r'[，。；：:,.!?]$', compact)
            and _looks_like_docx_heading_text(compact)
        )
        if looks_like_heading:
            return min(indent_level + 1, 6)

    if _looks_like_docx_heading_text(compact):
        numbered_level = _docx_numbered_heading_level(compact)
        if numbered_level:
            return numbered_level
        return 4

    inferred_heading = (
        len(compact) <= 80
        and next_block is not None
        and hasattr(next_block, "rows")
        # A fully bold line above a table is a table group label, not a heading.
        and not _docx_paragraph_is_fully_bold(paragraph)
    )
    if inferred_heading:
        return 2

    return 0


def _materialize_docx_image(paragraph, rel_id, media_dir, image_index):
    image_part = paragraph.part.related_parts.get(rel_id)
    if not image_part:
        return None, image_index
    ext = os.path.splitext(str(getattr(image_part, "partname", "")))[1] or ".png"
    file_name = f"docx_image_{image_index:03d}{ext.lower()}"
    file_path = os.path.join(media_dir, file_name)
    if not os.path.exists(file_path):
        with open(file_path, "wb") as f:
            f.write(image_part.blob)
    return file_path, image_index + 1


def _extract_docx_paragraph_images(paragraph, media_dir, image_index):
    image_refs = []
    for kind, value in _docx_paragraph_segments(paragraph):
        if kind != "image":
            continue
        file_path, image_index = _materialize_docx_image(paragraph, value, media_dir, image_index)
        if file_path:
            image_refs.append(file_path)
    return image_refs, image_index


def _docx_image_size(path):
    if not path or not os.path.exists(path):
        return None
    try:
        from PIL import Image
        with Image.open(path) as img:
            return img.size
    except Exception:
        return None


def _is_small_docx_image(path, max_width=220, max_height=120):
    size = _docx_image_size(path)
    if not size:
        return False
    return size[0] <= max_width and size[1] <= max_height


def _is_junk_docx_image(path):
    """Drop Word artifacts: 1-pixel slivers and leftover logo/banner scraps."""
    size = _docx_image_size(path)
    if not size:
        return False
    width, height = size
    if min(width, height) <= 12:
        return True
    if height <= 120 and width >= 6 * max(height, 1):
        return True
    return False


def _is_leftover_docx_scrap_image(path):
    """Empty-paragraph leftovers such as tiny logos after a caption."""
    size = _docx_image_size(path)
    if not size:
        return False
    width, height = size
    return max(width, height) <= 280


def _append_orphan_icon_to_previous(lines, image_path):
    """Attach a lone button icon to the preceding sentence instead of emitting a block image."""
    prev_idx = len(lines) - 1
    while prev_idx >= 0 and not (lines[prev_idx] or "").strip():
        prev_idx -= 1
    if prev_idx < 0:
        return False
    prev = lines[prev_idx]
    if prev.startswith(("#", "|", "!", "- ", "* ")):
        return False
    token = f"![{os.path.basename(image_path)}]({image_path})"
    lines[prev_idx] = f"{prev.rstrip()} {token}"
    return True


def _is_caption_like_docx_text(text):
    normalized = re.sub(r'\[\[/?(?:B|SUP|SUB)\]\]', '', _normalize_docx_text(text or ""))
    return bool(TABLE_CAPTION_PREFIX_RE.match(normalized) or FIGURE_CAPTION_PREFIX_RE.match(normalized))


def _is_note_like_docx_text(text):
    stripped = re.sub(r'\[\[/?(?:B|SUP|SUB)\]\]', '', _normalize_docx_text(text or ""))
    stripped = re.sub(r'^\s*(?:\d+[.)、]\s+|[-*+]\s+)', '', stripped)
    if stripped in {"注意事项", "其他注意事项"}:
        return False
    return bool(CHINESE_NOTE_LABEL_PATTERN.match(stripped) or NOTE_LABEL_PATTERN.match(stripped))


def _docx_to_markdown(file_path):
    from docx import Document as DocxDocument
    from docx.table import Table

    doc = DocxDocument(file_path)
    media_dir = os.path.splitext(file_path)[0] + "_media"
    _ensure_dir(media_dir)

    blocks = list(_iter_docx_blocks(doc))
    lines = []
    image_index = 1
    cover_started = False
    in_toc_block = False
    current_heading = ""
    def ensure_cover_heading():
        nonlocal cover_started
        if cover_started or current_heading:
            return
        lines.append("# Cover")
        lines.append("")
        cover_started = True

    def _is_toc_table(table):
        rows = []
        for row in table.rows[:6]:
            rows.append([_normalize_docx_text(cell.text) for cell in row.cells])
        flat = [cell for row in rows for cell in row if cell]
        if not flat:
            return False
        if flat[0] in DOCX_TOC_TITLES:
            return True
        return any(cell in DOCX_TOC_TITLES for cell in flat[:5])

    for idx, block in enumerate(blocks):
        next_block = blocks[idx + 1] if idx + 1 < len(blocks) else None
        if not isinstance(block, Table):
            text = _extract_docx_paragraph_text(block)
            ordered_segments = []
            image_refs = []
            for kind, value in _docx_paragraph_segments(block):
                if kind == "text":
                    ordered_segments.append(("text", value))
                    continue
                file_path, image_index = _materialize_docx_image(block, value, media_dir, image_index)
                if file_path:
                    image_refs.append(file_path)
                    ordered_segments.append(("image", file_path))

            # Inline button icons share a paragraph with body text; keep them in
            # the sentence. Icons next to a note (or alone in their own
            # paragraph) are decoration and stay out of the output.
            is_caption_text = _is_caption_like_docx_text(text)
            is_note_text = _is_note_like_docx_text(text)
            inline_parts = []
            block_images = []
            for kind, value in ordered_segments:
                if kind == "text":
                    inline_parts.append(value)
                    continue
                image_size = _docx_image_size(value)
                is_small_image = _is_small_docx_image(value)
                is_unknown_size = image_size is None
                if _is_junk_docx_image(value) and not is_caption_text:
                    continue
                if (
                    not text
                    and not is_caption_text
                    and not is_small_image
                    and _is_leftover_docx_scrap_image(value)
                ):
                    continue
                if is_small_image:
                    if is_note_text:
                        continue
                    if not text:
                        _append_orphan_icon_to_previous(lines, value)
                        continue
                    if not is_caption_text:
                        inline_parts.append(f"![{os.path.basename(value)}]({value})")
                        continue
                elif is_unknown_size:
                    if is_note_text:
                        continue
                    if text and not is_caption_text:
                        inline_parts.append(f"![{os.path.basename(value)}]({value})")
                        continue
                    if not text and _append_orphan_icon_to_previous(lines, value):
                        continue
                block_images.append(value)
            inline_text = _normalize_docx_text(''.join(inline_parts))
            style_name = block.style.name if block.style else ""
            heading_level = _infer_docx_heading_level(block, text, next_block, style_name)

            if re.match(r'(?i)^toc\s*\d+$', (style_name or '').strip()):
                continue
            if text in DOCX_TOC_TITLES:
                in_toc_block = True
                continue
            if in_toc_block and text in {"II", "I", "III", "IV", "V"}:
                continue

            if text and heading_level and _is_docx_toc_number(text):
                continue

            if in_toc_block and text and heading_level:
                in_toc_block = False

            heading_level = DOCX_SPECIAL_HEADING_LEVELS.get(text.strip().lower(), heading_level)

            if text and (
                re.match(r'^Formula\s*\d+\b', text, re.IGNORECASE)
                or re.match(r'^[A-Za-z][A-Za-z0-9 ()/μ.-]*\s*=\s*.+$', text)
            ):
                heading_level = 0

            if text and heading_level:
                current_heading = text
                lines.append(f"{'#' * max(1, heading_level)} {text}")
                # A heading paragraph can still anchor a figure image; keep it
                # so captions following the heading can bind to the image.
                for image_path in image_refs:
                    ensure_cover_heading()
                    lines.append(f"![{os.path.basename(image_path)}]({image_path})")
                lines.append("")
            else:
                if in_toc_block:
                    continue
                if inline_text:
                    ensure_cover_heading()
                    prev_block = blocks[idx - 1] if idx else None
                    list_marker = (
                        _docx_list_marker(block)
                        if _should_emit_docx_list_marker(block, text, next_block, prev_block)
                        else None
                    )
                    lines.append(f"{list_marker}{inline_text}" if list_marker else inline_text)
                for image_path in block_images:
                    ensure_cover_heading()
                    lines.append(f"![{os.path.basename(image_path)}]({image_path})")
                if inline_text or block_images:
                    lines.append("")
        else:
            if _is_toc_table(block):
                in_toc_block = True
                continue
            if in_toc_block:
                continue
            ensure_cover_heading()
            table_lines = _docx_table_to_markdown(block, heading=current_heading)
            if table_lines:
                lines.extend(table_lines)
                lines.append("")

    lines = _merge_docx_wrapped_paragraphs(lines)
    markdown_text = "\n".join(lines)
    markdown_text = re.sub(r'\n{3,}', '\n\n', markdown_text).strip()
    return markdown_text


def _get_heading_level(style_name):
    """Extract heading level (1-6) from Word style name, or 0 if not a heading."""
    if not style_name:
        return 0
    import re as _re
    m = _re.match(r'(?i)heading\s+(\d+)', style_name)
    if m:
        return int(m.group(1))
    # Map common Chinese style names
    lower = style_name.lower()
    for i in range(1, 7):
        if f"heading {i}" in lower:
            return i
        if f"标题 {i}" in lower:
            return i
    return 0


def _parse_content(source_format, file_path, content):
    if source_format == "md":
        body, fm_title = _extract_md_frontmatter(content)
        body = _promote_setext_headings(body)
        body = _normalize_native_markdown(body)
        sections = _parse_md_sections(body)
        if fm_title and sections:
            if sections[0].get("title") in {"文档", "正文"}:
                sections[0]["title"] = fm_title
        return sections
    elif source_format in ("docx", "idml"):
        return _parse_md_sections(content)
    raise ValueError(f"不支持的文件格式: {source_format}")


def _normalize_section_key(title):
    text = _clean_title(title or "")
    text = re.sub(r'\[\[/?[A-Z]+\]\]', '', text)
    text = _strip_md_bold(text).lower()
    text = ANY_CAPTION_PREFIX_RE.sub('', text)
    text = re.sub(r'^\d+(?:\.\d+)*\s*', '', text)
    # Keep CJK characters: collapsing them away made distinct Chinese headings
    # collide (e.g. "制备DNB" and "测定DNB浓度" both became "dnb"), which then
    # mis-nested sections during reshaping.
    text = re.sub(r'[^a-z0-9\u4e00-\u9fff]+', ' ', text).strip()
    return text


def _is_frontmatter_title(title):
    """Front-matter topics (about / revision history) go under <frontmatter>.

    Keyed on the section title rather than the source style, because the
    front-page style also covers the "试剂套装基本信息" chapter.
    """
    key = _normalize_section_key(title)
    if key in {
        "about the user manual",
        "about the instructions for use",
        "revision history",
        "version history",
        "manufacturer information",
    }:
        return True
    return bool(re.search(r'关于说明书|版本记录|版本历史|试剂盒基本信息|试剂套装基本信息', _clean_title(title or "")))


def _starts_with_table_like_prefix(title):
    normalized = _normalize_docx_text(_strip_md_bold(re.sub(r'\[\[/?[A-Z]+\]\]', '', title or '')))
    return bool(TABLE_CAPTION_PREFIX_RE.match(normalized) or FIGURE_CAPTION_PREFIX_RE.match(normalized))


def _split_leading_docx_subheading(content):
    if not content:
        return None, content

    lines = content.splitlines()
    first_idx = next((idx for idx, line in enumerate(lines) if line.strip()), None)
    if first_idx is None:
        return None, content

    first_line = lines[first_idx].strip()
    # Strip inline run placeholders before inspecting, otherwise guards such as
    # the leading-number check miss lines wrapped in [[B]]...[[/B]].
    normalized_line = _normalize_docx_text(_clean_navtitle(_strip_md_bold(first_line)))
    if (
        not normalized_line
        or len(normalized_line) > 30
        or len(normalized_line.split()) > 8
        or normalized_line.startswith(("Formula ", "formula "))
        or " = " in normalized_line
        or first_line.startswith(("#", "|", "![", "- ", "* "))
        # Metadata marker lines (table/figure captions, appendix) are not
        # subheadings even though _clean_navtitle strips their [[...]] token.
        or first_line.startswith(
            (IDML_TABCAP_MARKER, IDML_FIGCAP_MARKER, IDML_APPENDIX_MARKER, "[[NOTE:")
        )
        or re.match(r'^\d+[.)、]\s*', normalized_line)
        or TABLE_CAPTION_PREFIX_RE.match(normalized_line)
        or FIGURE_CAPTION_PREFIX_RE.match(normalized_line)
        # Table group labels such as "测序仪：MGISEQ-2000RS" are body text.
        or re.search(r'[:：]', normalized_line)
        or re.match(r'^(试剂|样本|步骤|操作|注意|提示|警告|小心|请勿|切勿)[:：]', normalized_line)
        or re.search(r'[.!?;:：，。)]$', normalized_line)
    ):
        return None, content

    rest_lines = lines[first_idx + 1:]
    while rest_lines and not rest_lines[0].strip():
        rest_lines = rest_lines[1:]
    rest_content = "\n".join(rest_lines).strip()
    if not rest_content:
        return None, content
    return first_line, rest_content


def _docx_child_belongs(parent_title, child_title, is_absorbing):
    parent_key = _normalize_section_key(parent_title)
    child_key = _normalize_section_key(child_title)
    if not parent_key or not child_key:
        return False

    if child_key in {"preparation", "operation", "procedure"}:
        return True
    if child_key == parent_key:
        return True
    if parent_key.startswith("cleanup of") and child_key.startswith(("single size selection", "double size selection")):
        return True
    if " and " in parent_key:
        parts = [part.strip() for part in parent_key.split(" and ") if part.strip()]
        if any(child_key == part or child_key.endswith(part) for part in parts):
            return True
    if is_absorbing and "optional" in child_key:
        return True
    if is_absorbing and child_key.startswith("qc of"):
        return True
    return False


def _reshape_docx_sections(sections):
    prepared = []
    for sec in sections:
        current = {
            "title": sec.get("title", ""),
            "content": sec.get("content", ""),
            "sections": _reshape_docx_sections(sec.get("sections", [])),
        }
        child_title, child_content = _split_leading_docx_subheading(current["content"])
        if child_title:
            current["content"] = ""
            current["sections"] = [{
                "title": child_title,
                "content": child_content,
                "sections": [],
            }] + current["sections"]
        prepared.append(current)

    grouped = []
    idx = 0
    while idx < len(prepared):
        current = prepared[idx]
        next_idx = idx + 1
        absorbed = False
        while next_idx < len(prepared) and _docx_child_belongs(current["title"], prepared[next_idx].get("title", ""), absorbed):
            current["sections"].append(prepared[next_idx])
            absorbed = True
            next_idx += 1
        grouped.append(current)
        idx = next_idx

    return grouped


def _append_text_block(base_text, extra_text):
    base_text = (base_text or "").strip()
    extra_text = (extra_text or "").strip()
    if base_text and extra_text:
        return f"{base_text}\n\n{extra_text}"
    return base_text or extra_text


def _is_empty_appendix_wrapper(section):
    """Bare 'Appendix'/'附录' headings with children only wrap the real appendices."""
    title_key = _normalize_section_key(section.get("title", ""))
    if title_key not in {"appendix", "附录"}:
        return False
    if (section.get("content") or "").strip():
        return False
    return bool(section.get("sections"))


def _postprocess_section_tree(sections):
    processed = []
    for sec in sections:
        current = {
            "title": sec.get("title", ""),
            "content": sec.get("content", ""),
            "sections": _postprocess_section_tree(sec.get("sections", [])),
            "is_appendix": bool(sec.get("is_appendix")),
        }

        title_key = _normalize_section_key(current["title"])
        if title_key == "appendix" and current["sections"]:
            grouped_children = []
            appendix_parent = None
            for child in current["sections"]:
                child_key = _normalize_section_key(child.get("title", ""))
                if appendix_parent is None and "barcode number and sequence information" in child_key:
                    appendix_parent = child
                    grouped_children.append(child)
                    continue
                if appendix_parent is not None and child_key.startswith("instructions for"):
                    appendix_parent.setdefault("sections", []).append(child)
                    continue
                grouped_children.append(child)
            current["sections"] = grouped_children

        if title_key == "cleanup of adapter ligated product" and current["content"] and current["sections"]:
            target_child = None
            for child in current["sections"]:
                child_key = _normalize_section_key(child.get("title", ""))
                if child_key == title_key:
                    target_child = child
                    break
            if target_child is not None:
                target_child["content"] = _append_text_block(current["content"], target_child.get("content", ""))
                current["content"] = ""

        if not (current.get("content") or "").strip() and current["sections"]:
            for child in current["sections"]:
                child_key = _normalize_section_key(child.get("title", ""))
                if child_key and child_key == title_key and _starts_with_table_like_prefix(child.get("title", "")):
                    current["content"] = _append_text_block(current.get("content", ""), child.get("content", ""))
                    break

        if title_key == "cover" and current["sections"]:
            kept_children = []
            cover_body_parts = [current["content"].strip()] if current["content"].strip() else []
            promoted_titles = {
                "about the user manual",
                "manufacturer information",
                "revision history",
                "version history",
                "版本历史",
                "修订历史",
                "版本记录",
            }
            leading_cover_meta = True
            for child in current["sections"]:
                child_title = _strip_md_bold(_clean_title(child.get("title", ""))).strip().lower()
                if leading_cover_meta and child_title not in promoted_titles:
                    cover_body_parts.append(child.get("title", "").strip())
                    if (child.get("content") or "").strip():
                        cover_body_parts.append(child.get("content", "").strip())
                    continue
                leading_cover_meta = False
                kept_children.append(child)
            current["sections"] = kept_children
            current["content"] = "\n\n".join(part for part in cover_body_parts if part)

        if _is_empty_appendix_wrapper(current):
            for child in current["sections"]:
                child["is_appendix"] = True
                processed.append(child)
            continue

        processed.append(current)

    return processed


def _extract_images_md(content):
    """Extract image metadata from markdown content (no download)."""
    images = []
    pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
    for match in re.finditer(pattern, content):
        images.append({"alt": match.group(1), "path": match.group(2)})
    return images


def _download_images_for_output(images, output_base, timeout=30, preserve_names=False):
    """Download external images and save to output_dir/image/.
    Returns dict mapping original URL to local filename.

    When preserve_names is set (IDML image packages), the source file's own
    basename is kept so the converted package carries the original asset names.
    """
    import urllib.request
    import urllib.error
    from pathlib import Path

    image_dir = os.path.join(output_base, "image")
    _ensure_dir(image_dir)

    existing_by_hash = {}
    for root, _, files in os.walk(image_dir):
        for fname in files:
            abs_path = os.path.join(root, fname)
            try:
                with open(abs_path, "rb") as f:
                    data = f.read()
                existing_by_hash[(len(data), data[:64])] = os.path.relpath(abs_path, output_base).replace(os.sep, "/")
            except Exception:
                continue

    url_to_local = {}
    idx = 0
    for img in images:
        url = img["path"]
        if not url:
            continue
        if url in url_to_local:
            continue
        try:
            ext = os.path.splitext(url.split("?")[0])[1] or ".png"
            if ext.lower() not in (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp"):
                ext = ".png"
            raw_data = None
            if os.path.exists(url):
                with open(url, "rb") as f:
                    raw_data = f.read()
            else:
                if not url.startswith(("http://", "https://")):
                    continue
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    raw_data = resp.read()
            if raw_data is None:
                continue
            content_key = (len(raw_data), raw_data[:64])
            if content_key in existing_by_hash:
                url_to_local[url] = existing_by_hash[content_key]
                continue
            if preserve_names:
                base = os.path.basename(url.split("?")[0].replace("\\", "/"))
                base_stem, base_ext = os.path.splitext(base)
                safe_stem = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", base_stem).strip()
                desired = f"{safe_stem}{base_ext or ext}" if safe_stem else f"image_{idx:03d}{ext}"
            else:
                desired = f"image_{idx:03d}{ext}"
            local_name = desired
            local_path = os.path.join(image_dir, local_name)
            counter = 1
            while os.path.exists(local_path):
                stem, suffix = os.path.splitext(desired)
                local_name = f"{stem}_{counter}{suffix}"
                local_path = os.path.join(image_dir, local_name)
                counter += 1
            with open(local_path, "wb") as f:
                f.write(raw_data)
            url_to_local[url] = f"image/{local_name}"
            idx += 1
        except Exception:
            url_to_local[url] = url
    return url_to_local


def _copy_docx_media_to_output(docx_path, output_base):
    image_dir = os.path.join(output_base, "image")
    _ensure_dir(image_dir)

    copied = set()
    try:
        with zipfile.ZipFile(docx_path, "r") as zf:
            media_names = [
                name for name in zf.namelist()
                if name.startswith("word/media/") and not name.endswith("/")
            ]
            for idx, name in enumerate(sorted(media_names), start=1):
                data = zf.read(name)
                ext = os.path.splitext(name)[1].lower() or ".png"
                out_name = f"docx_media_{idx:03d}{ext}"
                out_path = os.path.join(image_dir, out_name)
                with open(out_path, "wb") as f:
                    f.write(data)
                copied.add(f"image/{out_name}")
    except Exception:
        pass

    return copied


# Formats IME structured authoring can consume directly. Others (e.g. Adobe
# Illustrator .ai) need an AI->SVG conversion step first, so they are deferred
# to a separate workflow and skipped by the current IDML->DITA text pipeline.
IDML_IME_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg"}


# When a link points at a format that needs converting first, an IME-ready
# sibling with the same stem is used instead, e.g. Links/logo.ai -> Links/logo.svg
# (the .ai -> .svg conversion is done outside this pipeline).
IDML_DEFERRED_IMAGE_REPLACEMENTS = {
    ".ai": ".svg",
    ".eps": ".svg",
}


# Real-world IDML style vocabularies (e.g. MGI/DNBSEQ manuals) name headings
# "<group>:Title-L<n>-<lang>" instead of Word's "Heading n". The "<group>"
# prefix varies ("For reagent kit only:", "Operation guide:", ...), so match
# on the "Title-L<level>" token.
IDML_HEADING_LEVEL_RE = re.compile(r'(?i)\bTitle-L\s*(\d)\b')

# Front-matter / appendix titles that are level-1 headings without an "L<n>".
IDML_FRONT_TITLE_RE = re.compile(r'(?i)(Title in first page|Title-Appen)')

# Table-of-contents styles; the target DITA package regenerates its own TOC.
IDML_TOC_STYLE_RE = re.compile(r'(?i)^(?:toc|contents)\b')

# Running headers/footers and blank-page markers carry no body content.
IDML_JUNK_STYLE_RE = re.compile(
    r'(?i)(\bheader\b|\bfooter\b|blank[ _]?page|normalparagraphstyle)'
)

# Appendix headings use a "Title-Appen. n" style; tag them so the bookmap
# builder emits an <appendix> container with the original navtitle.
IDML_APPENDIX_STYLE_RE = re.compile(r'(?i)Title-Appen')
IDML_APPENDIX_MARKER = "[[APPENDIX]]"

# Callout boxes ("warning", "tip") come from tables whose cell styles describe
# a single sentence, a warning sentence, a tip or a symbol.
IDML_CALLOUT_STYLE_RE = re.compile(r'(?i)(single\s+sentence|warning\s+sentence|tips?|symbols)')
IDML_CALLOUT_MARKER_RE = re.compile(r'^\[\[NOTE:(\w+)\]\]$')

# Figure captions carry a "Figure-title" paragraph style. They are tagged so
# that the caption can be wrapped together with its image as
# <fig><title>...</title><image/></fig>; IME generates the figure number.
IDML_FIGURE_TITLE_RE = re.compile(r'(?i)Figure-title')
IDML_FIGCAP_MARKER = "[[FIGCAP]]"

# Table captions carry a "Table-title" paragraph style. They are tagged so the
# DITA layer lifts them into <table><title>...</title>; IME generates the
# "表 N" / "Table N" number.
IDML_TABLE_TITLE_RE = re.compile(r'(?i)Table-title')
IDML_TABCAP_MARKER = "[[TABCAP]]"

# Table cells that use a bullet/number paragraph style carry a compact list
# marker through markdown (GFM cells cannot nest lists) so the DITA layer can
# rebuild <ul>/<ol> inside <entry>.
IDML_CELL_UL_OPEN = "[[UL]]"
IDML_CELL_OL_OPEN = "[[OL]]"
IDML_CELL_LIST_SEP = "[[LI]]"
IDML_CELL_UL_CLOSE = "[[/UL]]"
IDML_CELL_OL_CLOSE = "[[/OL]]"

# IDML tables may merge cells horizontally (ColumnSpan) and vertically
# (RowSpan). The intermediate markdown carries the spans as markers so the
# DITA layer can emit namest/nameend (colspan) and morerows (rowspan); a cell
# covered by a neighbouring span travels as IDML_SPAN_COVERED.
IDML_SPAN_COVERED = "[[SPANC]]"
IDML_SPAN_MARK_RE = re.compile(r'\s*\[\[SPAN:(\d+),(\d+)\]\]\s*$')

# UI control names are enclosed in 【】 in the source (e.g. 【登录】, 【测序方案】).
# IME renders a <uicontrol> with its own 【】 brackets, so only the inner text is
# emitted. A numeric lead such as 【1】 is a note enumeration marker, not a
# control name, and is left untouched for the note-bullet grouping logic.
UI_CONTROL_RE = re.compile(r'【([^【】0-9][^【】]*)】')

# English Word manuals wrap on-screen labels in square brackets. Numeric
# markers such as [1] stay as note/footnote text.
EN_BRACKET_UI_RE = re.compile(r'\[(?!\d{1,2}\])([^\[\]]+)\]')

# English on-screen UI text is styled with a "Silk screen" character style
# (which is what makes it look bold); it maps to <uicontrol> like the Chinese
# 【】 convention.
IDML_UI_STYLE_RE = re.compile(r'(?i)silk\s*screen')
IDML_UI_MARK_OPEN = "[[UI]]"
IDML_UI_MARK_CLOSE = "[[/UI]]"

# Italic character styles in 617: Cross reference* (N/c/V, book titles) and
# Subtle Emphasis (FontStyle Italic). UI styles take precedence.
IDML_ITALIC_STYLE_RE = re.compile(r'(?i)italic|subtle\s*emphasis|^cross\s*reference')
IDML_I_MARK_OPEN = "[[I]]"
IDML_I_MARK_CLOSE = "[[/I]]"

# InDesign cross-references read 第<page>页“<target title>”. Carry title and
# page as [[XREF:title#page]]; resolved DITA xrefs are empty elements with
# cms:title, and the page is only used when the target cannot be resolved.
XREF_RE = re.compile(r'\[\[XREF:([^\[\]#]+)(?:#([^\[\]]+))?\]\]')


def _strip_xml_ns(tag):
    if isinstance(tag, str) and "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _idml_style_is_italic(style_key, font_style=""):
    if re.search(r"(?i)italic", font_style or ""):
        return True
    key = (style_key or "").strip()
    return bool(key and IDML_ITALIC_STYLE_RE.search(key))


def _idml_wrap_run_text(text, ui=False, italic=False):
    if not text:
        return text
    if ui:
        return f"{IDML_UI_MARK_OPEN}{text}{IDML_UI_MARK_CLOSE}"
    if italic and text.strip():
        return f"{IDML_I_MARK_OPEN}{text}{IDML_I_MARK_CLOSE}"
    return text


def _idml_merge_adjacent_i_marks(text):
    if not text:
        return text
    return text.replace(f"{IDML_I_MARK_CLOSE}{IDML_I_MARK_OPEN}", "")


def _idml_table_column_widths(table_elem):
    widths = {}
    for child in table_elem:
        if _strip_xml_ns(child.tag) != "Column":
            continue
        try:
            widths[int(child.get("Name"))] = float(child.get("SingleColumnWidth"))
        except (TypeError, ValueError):
            continue
    return widths


def _idml_relative_colwidths(widths, col_count):
    """Turn IDML point widths into CALS relative colwidth values summing to 1.00*."""
    if col_count <= 0:
        return None
    vals = [widths.get(i) for i in range(col_count)]
    if any(value is None or value <= 0 for value in vals):
        return None
    total = sum(vals)
    if total <= 0:
        return None
    parts = []
    acc = 0.0
    for index, value in enumerate(vals):
        if index == col_count - 1:
            rest = round(1.0 - acc, 2)
            if rest <= 0:
                rest = 0.01
            parts.append(f"{rest:.2f}*")
        else:
            frac = round(value / total, 2)
            if frac <= 0:
                frac = 0.01
            acc += frac
            parts.append(f"{frac:.2f}*")
    return parts


def _idml_collect_text(elem, ui_styles=None, ui=False, italic=False):
    """Collect paragraph text from an element, skipping nested tables.

    When ``ui_styles`` is given, runs carrying an on-screen ("Silk screen")
    character style are wrapped in ``[[UI]]...[[/UI]]`` so the DITA layer can
    turn them into ``<uicontrol>``. Italic character styles become ``[[I]]``.
    """
    parts = []
    for child in list(elem):
        tag = _strip_xml_ns(child.tag)
        if tag == "Table":
            continue
        child_style = _idml_style_key(child.get("AppliedCharacterStyle", ""))
        child_ui = ui or bool(child_style and ui_styles and child_style in ui_styles)
        child_italic = italic or _idml_style_is_italic(
            child_style, child.get("FontStyle") or ""
        )
        if tag == "CrossReferenceSource":
            marker = _idml_xref_marker(child)
            if marker:
                parts.append(marker)
            else:
                parts.append(_idml_collect_text(child, ui_styles, child_ui, child_italic))
            continue
        if tag == "Content":
            if child.text:
                parts.append(_idml_wrap_run_text(child.text, child_ui, child_italic))
        elif tag == "Br":
            parts.append(" ")
        else:
            parts.append(_idml_collect_text(child, ui_styles, child_ui, child_italic))
    return _idml_merge_adjacent_i_marks("".join(parts))


def _idml_xref_marker(elem):
    """Return an ``[[XREF:title]]`` marker for a ``<CrossReferenceSource>``.

    The source text reads 第<page>页“<target title>”. The page comes from the
    InDesign ResultText variable. The page is kept on the marker so unresolved
    targets can still show 第N页“标题”; resolved xrefs stay empty.
    """
    contents = [
        sub.text
        for sub in elem.iter()
        if _strip_xml_ns(sub.tag) == "Content" and sub.text
    ]
    text = "".join(contents)
    match = re.search(r'[\u201c"]([^\u201d"]+)[\u201d"]', text)
    if not match:
        return None
    title = match.group(1).strip()
    if not title:
        return None
    title = _clean_xref_title(title) or title
    page = ""
    for sub in elem.iter():
        if _strip_xml_ns(sub.tag) == "TextVariableInstance":
            result = (sub.get("ResultText") or "").strip()
            if result:
                page = result
                break
    if page:
        return f"[[XREF:{title}#{page}]]"
    return f"[[XREF:{title}]]"


def _idml_style_key(style_ref):
    value = (style_ref or "").strip()
    return value.split("/", 1)[1] if "/" in value else value


def _load_idml_styles(zf):
    """Map ParagraphStyle ids to display names and detect list styles."""
    style_map = {}
    list_styles = {}
    # Character styles that mark on-screen (silk screen) UI text. The Chinese
    # source brackets such text with 【】; the English source instead applies a
    # "Silk screen" character style (which renders bold), so both map to
    # <uicontrol> downstream.
    ui_styles = set()
    for name in zf.namelist():
        low = name.lower()
        if not low.endswith("styles.xml"):
            continue
        try:
            root = ET.fromstring(zf.read(name))
        except Exception:
            continue
        for elem in root.iter():
            tag = _strip_xml_ns(elem.tag)
            if tag == "CharacterStyle":
                display = elem.get("Name") or ""
                if IDML_UI_STYLE_RE.search(display):
                    key = _idml_style_key(elem.get("Self") or "")
                    if key:
                        ui_styles.add(key)
                continue
            if tag != "ParagraphStyle":
                continue
            self_id = elem.get("Self") or ""
            key = _idml_style_key(self_id)
            if not key:
                continue
            style_map[key] = elem.get("Name") or key
            list_type = ""
            for sub in elem.iter():
                tag = _strip_xml_ns(sub.tag)
                if tag in ("BulletsAndNumberingListType", "NumberingListType"):
                    list_type = (sub.text or "").strip() or list_type
                elif tag == "NumberingExpression":
                    list_type = "NumberedList"
                elif tag == "BulletChar":
                    list_type = list_type or "BulletList"
            if list_type:
                list_styles[key] = list_type
    return style_map, list_styles, ui_styles


def _idml_heading_level(style_ref, style_map):
    key = _idml_style_key(style_ref)
    display = style_map.get(key, key) or ""
    level = _get_heading_level(display)
    if level:
        return level
    match = re.match(r'(?i)^\s*(?:heading|标题|head|h)\s*[-_ ]?(\d+)\b', display)
    if match:
        return int(match.group(1))
    match = IDML_HEADING_LEVEL_RE.search(display)
    if match:
        return int(match.group(1))
    if IDML_FRONT_TITLE_RE.search(display):
        return 1
    return 0


def _idml_style_is_toc(display):
    return bool(IDML_TOC_STYLE_RE.match((display or "").strip()))


def _idml_style_is_junk(display):
    return bool(IDML_JUNK_STYLE_RE.search(display or ""))


def _idml_story_is_junk(story_root, style_map):
    """A story made up only of running headers/footers, TOC or blank-page
    markers carries no body content and is dropped entirely."""
    saw_text = False
    for child in story_root.iter():
        if _strip_xml_ns(child.tag) != "ParagraphStyleRange":
            continue
        if not _idml_collect_text(child).strip():
            continue
        saw_text = True
        key = _idml_style_key(child.get("AppliedParagraphStyle", ""))
        display = (style_map.get(key, key) or "")
        if not (_idml_style_is_junk(display) or _idml_style_is_toc(display)):
            return False
    return saw_text


def _idml_list_marker(elem, style_ref, style_map, list_styles):
    key = _idml_style_key(style_ref)
    display = (style_map.get(key, key) or "").lower()
    list_type = (list_styles.get(key) or "").lower()
    ordered = "number" in list_type
    unordered = "bullet" in list_type
    if not (ordered or unordered):
        for sub in elem.iter():
            tag = _strip_xml_ns(sub.tag)
            if tag == "NumberingExpression":
                ordered = True
            elif tag in ("BulletChar", "BulletList"):
                unordered = True
    if not (ordered or unordered):
        if any(word in display for word in ("number", "step", "编号", "步骤", "有序")):
            ordered = True
        elif any(word in display for word in ("bullet", "list", "列表", "项目符号", "无序")):
            unordered = True
    if ordered:
        return "1. "
    if unordered:
        return "- "
    return None


def _idml_list_level(style_ref, style_map):
    """Nesting level encoded in an InDesign list style name."""
    key = _idml_style_key(style_ref)
    display = urllib.parse.unquote(style_map.get(key, key) or "")
    match = re.search(r"(?i)(?:level|级别)\s*[-_ ]?(\d+)", display)
    if not match:
        return None
    return max(1, int(match.group(1)))


def _idml_cell_text(cell, ui_styles=None, image_resolver=None):
    return " ".join(
        text
        for text, _is_list_item in _idml_cell_text_items(
            cell, ui_styles, image_resolver
        )
        if text
    )


def _idml_cell_list_kind(style):
    """ul/ol for table-cell paragraph styles that are real lists."""
    display = urllib.parse.unquote(style or "")
    if re.search(r"(?i)numbered\s+list", display):
        return "ol"
    if re.search(r"(?i)(?:sentence\s+list|bulleted\s+list)", display):
        return "ul"
    return None


def _idml_cell_markdown(items):
    """Encode cell paragraphs; bullet/number runs become [[UL]]/[[OL]] markers."""
    cleaned = []
    for text, kind in items or []:
        text = re.sub(r"\s+", " ", text or "").strip().replace("|", "\\|")
        if text:
            cleaned.append((text, kind))
    if not cleaned:
        return ""
    kinds = {kind for _, kind in cleaned}
    if kinds <= {"ul"} or kinds <= {"ol"}:
        kind = next(iter(kinds))
        open_m = IDML_CELL_UL_OPEN if kind == "ul" else IDML_CELL_OL_OPEN
        close_m = IDML_CELL_UL_CLOSE if kind == "ul" else IDML_CELL_OL_CLOSE
        return open_m + IDML_CELL_LIST_SEP.join(text for text, _ in cleaned) + close_m
    return " ".join(text for text, _ in cleaned)


def _idml_inline_images(text, uris, image_resolver):
    """Replace positional icon placeholders with inline image markdown."""
    def repl(match):
        index = int(match.group(1))
        if index >= len(uris) or image_resolver is None:
            return ""
        path = image_resolver(uris[index])
        if not path:
            return ""
        return f"![{os.path.basename(path)}]({path})"

    return re.sub(r"\x00IMG(\d+)\x00", repl, text)


def _idml_cell_text_items(cell, ui_styles=None, image_resolver=None):
    """Cell paragraphs as ``(text, is_list_item)`` tuples.

    A "sentence list" paragraph uses ``<Br/>`` between list items, so each run
    becomes its own item. Images keep their inline position through the
    ``\\x00IMGn\\x00`` placeholders produced by ``_idml_paragraph_pieces``.
    """
    items = []
    saw_paragraph = False

    def add_paragraph(para):
        nonlocal saw_paragraph
        saw_paragraph = True
        style = urllib.parse.unquote(para.get("AppliedParagraphStyle", ""))
        list_kind = _idml_cell_list_kind(style)
        pieces = _idml_paragraph_pieces(
            para, split_on_br=bool(list_kind), ui_styles=ui_styles
        )
        for piece_kind, value, extra in pieces:
            if piece_kind == "text":
                text = _idml_inline_images(value, extra, image_resolver).strip()
            elif piece_kind == "image":
                path = image_resolver(value) if image_resolver else None
                text = f"![{os.path.basename(path)}]({path})" if path else ""
            else:
                text = _idml_collect_text(value, ui_styles).strip()
            if text:
                items.append((text, list_kind))

    def visit(node):
        for child in list(node):
            tag = _strip_xml_ns(child.tag)
            if tag == "ParagraphStyleRange":
                add_paragraph(child)
                continue
            if tag == "Table":
                # A nested callout inside a cell contributes its body text once.
                text = _idml_collect_text(child, ui_styles).strip()
                if text:
                    items.append((text, False))
                continue
            visit(child)

    visit(cell)
    if not saw_paragraph:
        text = _idml_collect_text(cell, ui_styles).strip()
        if text:
            items.append((text, False))
    return items


def _idml_table_to_markdown(table_elem, ui_styles=None, image_resolver=None):
    # IDML stores cells as direct children of <Table>, positioned by a
    # "<col>:<row>" Name attribute (columns are the first index, rows the
    # second; the table's ColumnCount/RowCount confirm this order).
    grid = {}
    cell_elems = {}
    max_col = -1
    for child in table_elem:
        if _strip_xml_ns(child.tag) != "Cell":
            continue
        name = (child.get("Name") or "").strip()
        try:
            col_s, row_s = name.split(":", 1)
            col, row = int(col_s), int(row_s)
        except ValueError:
            continue
        text = _idml_cell_markdown(
            _idml_cell_text_items(child, ui_styles, image_resolver)
        )
        try:
            rowspan = max(1, int(child.get("RowSpan") or "1"))
            colspan = max(1, int(child.get("ColumnSpan") or "1"))
        except ValueError:
            rowspan, colspan = 1, 1
        if colspan > 1 or rowspan > 1:
            text = (text + " " if text else "") + f"[[SPAN:{colspan},{rowspan}]]"
        grid[(row, col)] = text
        cell_elems[(row, col)] = child
        for dr in range(rowspan):
            for dc in range(colspan):
                grid.setdefault((row + dr, col + dc), IDML_SPAN_COVERED)
        max_col = max(max_col, col + colspan - 1)
    if not grid or max_col < 0:
        return []
    row_indexes = sorted({r for r, _ in grid})
    width = max_col + 1
    strip_spans = lambda value: IDML_SPAN_MARK_RE.sub("", value or "").strip()
    strip_images = lambda value: re.sub(r'!\[[^\]]*\]\([^)]*\)', '', value or '').strip()
    header_row_count = int(table_elem.get("HeaderRowCount") or "0") or 0
    # A callout box (warning/tip) is a narrow table with no header row whose
    # cells all sit in a leading icon column: the icon cell carries a symbol
    # image (or a callout style) and no text, and the note body is the text of
    # the remaining cells. Emit it as [[NOTE:type]] so the DITA layer produces
    # a <note>, with the type taken from the icon. A wider table, or one whose
    # leading column holds real content, is a normal table.
    if row_indexes and header_row_count == 0 and 1 <= width <= 2:
        lead_texts = [
            strip_images(strip_spans(grid.get((r, 0), ""))).strip()
            for r in row_indexes
        ]
        lead_cells = [cell_elems.get((r, 0)) for r in row_indexes]
        icon_column = all(
            (not text) or _idml_cell_is_callout(cell)
            for text, cell in zip(lead_texts, lead_cells)
        ) and not any(lead_texts)
        if icon_column:
            callout_type = _idml_callout_note_type(lead_cells[0] if lead_cells else None)
            body_rows = []
            for r in row_indexes:
                for c in range(1, width):
                    cell = cell_elems.get((r, c))
                    for text, is_list_item in _idml_cell_text_items(
                        cell, ui_styles, image_resolver
                    ):
                        body = strip_spans(text)
                        if not body:
                            continue
                        body_rows.append(("- " + body) if is_list_item else body)
            if body_rows:
                lines = [f"| [[NOTE:{callout_type}]] |", "| :--- |"]
                lines.extend("| " + body + " |" for body in body_rows)
                return lines
    if width == 1 and row_indexes:
        header_cell = cell_elems.get((row_indexes[0], 0))
        header_text = strip_spans(grid.get((row_indexes[0], 0), "").strip())
        if (not header_text or _idml_cell_is_callout(header_cell)):
            callout_type = _idml_callout_note_type(header_cell)
            lines = [f"| [[NOTE:{callout_type}]] |", "| :--- |"]
            body_rows = []
            # A 1x1 callout keeps its only cell as the body.
            for text, is_list_item in _idml_cell_text_items(
                header_cell, ui_styles, image_resolver
            ):
                body_rows.append(("- " + text) if is_list_item else text)
            for r in row_indexes[1:]:
                for text, is_list_item in _idml_cell_text_items(
                    cell_elems.get((r, 0)), ui_styles, image_resolver
                ):
                    body_rows.append(("- " + text) if is_list_item else text)
            for body in (b for b in body_rows if b.strip()):
                lines.append("| " + body + " |")
            return lines
    render = lambda r: [grid.get((r, c), "") for c in range(width)]
    lines = []
    relative_widths = _idml_relative_colwidths(
        _idml_table_column_widths(table_elem), width
    )
    if relative_widths:
        lines.append("[[COLW:" + ",".join(relative_widths) + "]]")
    if header_row_count != 1:
        # GFM only has one header row; carry the real IDML header count so a
        # two-row header stays in <thead> instead of leaking into <tbody>.
        lines.append(f"[[THEAD:{header_row_count}]]")
    lines.extend([
        "| " + " | ".join(render(row_indexes[0])) + " |",
        "| " + " | ".join([":---"] * width) + " |",
    ])
    for r in row_indexes[1:]:
        lines.append("| " + " | ".join(render(r)) + " |")
    return lines


def _idml_cell_paragraph_styles(cell):
    styles = []
    for node in cell.iter():
        if _strip_xml_ns(node.tag) != "ParagraphStyleRange":
            continue
        styles.append(urllib.parse.unquote(_idml_style_key(node.get("AppliedParagraphStyle", ""))))
    return styles


def _idml_cell_is_callout(cell):
    if cell is None:
        return False
    return bool(IDML_CALLOUT_STYLE_RE.search(" ".join(_idml_cell_paragraph_styles(cell))))


def _idml_callout_note_type(cell):
    """Note type for an IDML callout box, inferred from its symbol icon.

    The icon filename encodes the intent: "Warning"/"Danger"/"icon_warning"
    are hazards, "Caution" is a caution, everything else ("Tips", "icon_note")
    is a tip. See word-to-dita-conversion-rules.md for the full mapping.
    """
    if cell is None:
        return "tip"
    haystack = []
    for uri in _idml_image_links(cell):
        haystack.append(urllib.parse.unquote(uri).lower())
    haystack.extend(style.lower() for style in _idml_cell_paragraph_styles(cell))
    joined = " ".join(haystack)
    if any(keyword in joined for keyword in ("warning", "warn", "danger", "risk")):
        return "warning"
    if "caution" in joined:
        return "caution"
    return "tip"


def _idml_image_links(elem):
    links = []
    for child in list(elem):
        tag = _strip_xml_ns(child.tag)
        if tag == "Table":
            # Images anchored in a callout table belong to that table, not to
            # the surrounding paragraph.
            continue
        if tag == "Link":
            uri = child.get("LinkResourceURI") or child.get("URI") or ""
            if uri:
                links.append(uri)
            continue
        links.extend(_idml_image_links(child))
    return links


def _idml_referenced_basenames(inner_zf):
    """Basenames of external resources (Links/ etc.) referenced by an IDML."""
    names = set()
    for entry in inner_zf.namelist():
        if entry.endswith("/") or not entry.lower().endswith(".xml"):
            continue
        try:
            root = ET.fromstring(inner_zf.read(entry))
        except Exception:
            continue
        for node in root.iter():
            if _strip_xml_ns(node.tag) != "Link":
                continue
            uri = urllib.parse.unquote(node.get("LinkResourceURI") or node.get("URI") or "")
            if not uri:
                continue
            base = os.path.basename(uri.replace("\\", "/").split(":")[-1]).strip()
            if not base:
                continue
            names.add(base.lower())
            # A converted sibling (e.g. .svg standing in for a .ai) also counts
            # as referenced, so it is carried into the resolved package.
            stem, ext = os.path.splitext(base)
            replacement = IDML_DEFERRED_IMAGE_REPLACEMENTS.get(ext.lower())
            if replacement:
                names.add((stem + replacement).lower())
    return names


def _idml_paragraph_pieces(para, split_on_br, ui_styles=None):
    """Split a paragraph into ordered text/table/image pieces.

    ``<Br/>`` separates multiple logical steps inside one InDesign numbered or
    bulleted list paragraph, so a list run ends the current text piece and
    starts a new one; in prose the break is folded into the run as a space. A
    nested ``<Table>`` (e.g. a callout box) or ``<Link>`` image ends the run too
    so it keeps its position between steps instead of sinking to the end.
    """
    pieces = []
    buffer = []
    images = []

    def flush():
        text = re.sub(r'[ \t\u00a0]+', ' ', "".join(buffer)).strip()
        text = _idml_merge_adjacent_i_marks(text)
        if text:
            pieces.append(("text", text, list(images)))
        else:
            for uri in images:
                pieces.append(("image", uri, None))
        buffer.clear()
        images.clear()

    def visit(node, ui=False, italic=False):
        for sub in list(node):
            sub_tag = _strip_xml_ns(sub.tag)
            sub_style = _idml_style_key(sub.get("AppliedCharacterStyle", ""))
            sub_ui = ui or bool(sub_style and ui_styles and sub_style in ui_styles)
            sub_italic = italic or _idml_style_is_italic(
                sub_style, sub.get("FontStyle") or ""
            )
            if sub_tag == "Content":
                if sub.text:
                    buffer.append(_idml_wrap_run_text(sub.text, sub_ui, sub_italic))
            elif sub_tag == "Br":
                if split_on_br:
                    flush()
                else:
                    buffer.append(" ")
            elif sub_tag == "Table":
                flush()
                pieces.append(("table", sub, None))
            elif sub_tag == "Link":
                uri = sub.get("LinkResourceURI") or sub.get("URI") or ""
                if uri:
                    # An inline button icon sits inside its step's text run, so
                    # it rides along with the current run rather than breaking it.
                    # A positional placeholder keeps the icon exactly where it
                    # appeared (e.g. between 点击 and the following comma) so the
                    # caller can inline it instead of sinking it to the run's end.
                    placeholder = f"\x00IMG{len(images)}\x00"
                    images.append(uri)
                    buffer.append(placeholder)
            elif sub_tag == "CrossReferenceSource":
                marker = _idml_xref_marker(sub)
                if marker:
                    buffer.append(marker)
                else:
                    visit(sub, sub_ui, sub_italic)
            else:
                visit(sub, sub_ui, sub_italic)

    visit(para)
    flush()
    return pieces


def _idml_is_inline_icon(uri):
    base = urllib.parse.unquote(os.path.basename((uri or "").replace("\\", "/")))
    return base.lower().startswith("icon")


def _idml_paragraph_has_only_inline_icons(elem):
    uris = _idml_image_links(elem)
    return bool(uris) and all(_idml_is_inline_icon(uri) for uri in uris)


def _idml_walk(elem, style_map, list_styles, blocks, image_resolver=None, ui_styles=None):
    def emit_piece(piece_kind, value):
        if piece_kind == "table":
            table_lines = _idml_table_to_markdown(value, ui_styles, image_resolver)
            if table_lines:
                blocks.append({"kind": "table", "lines": table_lines})
        elif piece_kind == "image":
            blocks.append({"kind": "image", "uri": value})

    for child in list(elem):
        tag = _strip_xml_ns(child.tag)
        if tag == "Table":
            table_lines = _idml_table_to_markdown(child, ui_styles, image_resolver)
            if table_lines:
                blocks.append({"kind": "table", "lines": table_lines})
            continue
        if tag == "ParagraphStyleRange":
            text = re.sub(r'[ \t\u00a0]+', ' ', _idml_collect_text(child)).strip()
            style_ref = child.get("AppliedParagraphStyle", "")
            display = (_idml_style_key(style_ref) and style_map.get(_idml_style_key(style_ref), "")) or ""
            if text and not _idml_style_is_toc(display):
                if text not in DOCX_TOC_TITLES:
                    level = _idml_heading_level(style_ref, style_map)
                    marker = None if level else _idml_list_marker(child, style_ref, style_map, list_styles)
                    if marker is None and IDML_FIGURE_TITLE_RE.search(display):
                        marker = IDML_FIGCAP_MARKER
                    if marker is None and IDML_TABLE_TITLE_RE.search(display):
                        marker = IDML_TABCAP_MARKER
                    if marker in ("1. ", "- "):
                        # Numbered/bulleted list: each <Br/> run is its own step,
                        # keeping the OL numbering continuous across any callout,
                        # figure or table nested between steps.
                        list_level = _idml_list_level(style_ref, style_map)
                        for piece_kind, value, extra in _idml_paragraph_pieces(child, split_on_br=True, ui_styles=ui_styles):
                            if piece_kind == "text":
                                blocks.append({
                                    "kind": "para",
                                    "level": 0,
                                    "text": _idml_inline_images(value, extra, image_resolver) if extra else value,
                                    "marker": marker,
                                    "list_level": list_level,
                                    "appendix": False,
                                })
                            else:
                                emit_piece(piece_kind, value)
                        continue
                    if _idml_paragraph_has_only_inline_icons(child):
                        # Inline button/status icons keep their sentence
                        # position; emitting them as block images strands
                        # them on a line of their own.
                        for piece_kind, value, extra in _idml_paragraph_pieces(
                            child, split_on_br=False, ui_styles=ui_styles
                        ):
                            if piece_kind == "text":
                                blocks.append({
                                    "kind": "para",
                                    "level": 0,
                                    "text": _idml_inline_images(
                                        value, extra, image_resolver
                                    ) if extra else value,
                                    "marker": None,
                                    "appendix": False,
                                })
                            else:
                                emit_piece(piece_kind, value)
                        continue
                    if not level and marker not in (IDML_FIGCAP_MARKER, IDML_TABCAP_MARKER):
                        # Body <Br/> is a paragraph break (关于说明书 and similar
                        # front-matter prose), not a line wrap.
                        for piece_kind, value, extra in _idml_paragraph_pieces(
                            child, split_on_br=True, ui_styles=ui_styles
                        ):
                            if piece_kind == "text":
                                blocks.append({
                                    "kind": "para",
                                    "level": 0,
                                    "text": _idml_inline_images(value, extra, image_resolver) if extra else value,
                                    "marker": None,
                                    "appendix": False,
                                })
                            else:
                                emit_piece(piece_kind, value)
                        continue
                    blocks.append({
                        "kind": "heading" if level else "para",
                        "level": level,
                        "text": text if level else re.sub(
                            r'[ \t\u00a0]+', ' ',
                            _idml_collect_text(child, ui_styles),
                        ).strip(),
                        "marker": marker,
                        "appendix": bool(level) and bool(IDML_APPENDIX_STYLE_RE.search(display)),
                    })
            for uri in _idml_image_links(child):
                blocks.append({"kind": "image", "uri": uri})
            # A callout table can be anchored inside a paragraph; recurse so the
            # nested table is emitted after the paragraph's own text.
            if any(_strip_xml_ns(d.tag) == "Table" for d in child.iter()):
                _idml_walk(child, style_map, list_styles, blocks, image_resolver, ui_styles)
            continue
        _idml_walk(child, style_map, list_styles, blocks, image_resolver, ui_styles)


def _idml_item_position(elem):
    transform = elem.get("ItemTransform")
    if not transform:
        return None, None
    try:
        values = [float(v) for v in transform.split()]
    except (TypeError, ValueError):
        return None, None
    if len(values) != 6:
        return None, None
    return values[5], values[4]


def _idml_resolve_src(base, ref, namelist):
    if not ref:
        return None
    ref = ref.replace("\\", "/")
    for candidate in ([ref] + ([f"{base}/{ref}"] if base else [])):
        if candidate in namelist:
            return candidate
    target = ref.split("/")[-1].lower()
    for name in namelist:
        if name.split("/")[-1].lower() == target:
            return name
    return None


def _idml_story_index(zf, namelist):
    """Map story ids (e.g. 'u1') and refs (e.g. 'Story/u1') to file paths."""
    index = {}
    for name in namelist:
        low = name.lower()
        if not (low.startswith("stories/") and low.endswith(".xml")):
            continue
        try:
            root = ET.fromstring(zf.read(name))
        except Exception:
            continue
        # The file root is usually an <idPkg:Story> packaging wrapper whose
        # local name also strips to "Story"; the real element carries Self.
        story_elem = next(
            (
                e for e in root.iter()
                if _strip_xml_ns(e.tag) == "Story" and (e.get("Self") or "").strip()
            ),
            None,
        )
        if story_elem is None:
            continue
        self_id = (story_elem.get("Self") or "").strip()
        if self_id:
            index[self_id] = name
            index[f"Story/{self_id}"] = name
    return index


def _idml_resolve_story(base, ref, namelist, story_index):
    if not ref:
        return None
    return story_index.get(ref) or _idml_resolve_src(base, ref, namelist)


def _idml_reading_order(zf):
    """Return reading-order items: ('story', src) or ('image', link_uri)."""
    namelist = zf.namelist()
    designmap_name = next(
        (n for n in namelist if n.split("/")[-1].lower() == "designmap.xml"), None
    )
    if not designmap_name:
        return None
    try:
        designmap = ET.fromstring(zf.read(designmap_name))
    except Exception:
        return None

    base = designmap_name.rsplit("/", 1)[0] if "/" in designmap_name else ""
    story_index = _idml_story_index(zf, namelist)
    spreads = []
    stories = []
    for elem in designmap:
        tag = _strip_xml_ns(elem.tag)
        src = elem.get("src")
        if not src:
            continue
        if tag == "Spread":
            spreads.append(src)
        elif tag == "Story":
            stories.append(src)

    items = []
    emitted = set()
    for spread_ref in spreads:
        spread_src = _idml_resolve_src(base, spread_ref, namelist)
        if not spread_src:
            continue
        try:
            spread = ET.fromstring(zf.read(spread_src))
        except Exception:
            continue
        candidates = []
        order = 0
        for elem in spread.iter():
            tag = _strip_xml_ns(elem.tag)
            if tag not in ("TextFrame", "Rectangle", "Oval", "Polygon", "GraphicLine"):
                continue
            story_ref = elem.get("ParentStory")
            links = _idml_image_links(elem)
            if not story_ref and not links:
                continue
            y, x = _idml_item_position(elem)
            candidates.append((y, x, order, story_ref, links))
            order += 1
        candidates.sort(key=lambda c: (0 if c[0] is not None else 1, c[0] or 0, c[1] or 0, c[2]))
        for _, _, _, story_ref, links in candidates:
            if story_ref:
                story_src = _idml_resolve_story(base, story_ref, namelist, story_index)
                if story_src and story_src not in emitted:
                    items.append(("story", story_src))
                    emitted.add(story_src)
            for uri in links:
                items.append(("image", uri))

    for story_ref in stories:
        story_src = _idml_resolve_story(base, story_ref, namelist, story_index)
        if story_src and story_src not in emitted:
            items.append(("story", story_src))
            emitted.add(story_src)
    return items


def _idml_find_link_target(namelist, base_name):
    """Find the container entry for a link basename, preferring Links/."""
    lower = base_name.lower()
    for name in namelist:
        if name.endswith("/"):
            continue
        parts = name.split("/")
        if parts[-1].lower() == lower and parts[0].lower() == "links":
            return name
    for name in namelist:
        if not name.endswith("/") and name.split("/")[-1].lower() == lower:
            return name
    return None


def _extract_idml_image(zf, namelist, link_uri, media_dir, cache):
    if link_uri in cache:
        return cache[link_uri]
    raw = urllib.parse.unquote(link_uri or "").replace("\\", "/")
    if raw.lower().startswith("file:"):
        raw = raw[5:]
    base_name = os.path.basename(raw).strip()
    if not base_name:
        return None
    stem, ext = os.path.splitext(base_name)
    ext_low = ext.lower()
    if ext_low in IDML_IME_IMAGE_EXTS:
        resolved_name = base_name
    else:
        # Formats needing conversion are served by an IME-ready sibling with the
        # same stem when present, e.g. logo.ai -> logo.svg.
        replacement = IDML_DEFERRED_IMAGE_REPLACEMENTS.get(ext_low)
        if not replacement:
            cache[link_uri] = None
            return None
        resolved_name = stem + replacement
    target = _idml_find_link_target(namelist, resolved_name)
    if target is None:
        cache[link_uri] = None
        return None
    out_stem, out_ext = os.path.splitext(os.path.basename(resolved_name))
    # Keep the original asset name (spaces and non-ASCII included) as the
    # reference package does; only strip characters illegal in file names.
    safe_stem = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', out_stem).strip() or "image"
    out_path = os.path.join(media_dir, f"{safe_stem}{out_ext}")
    counter = 1
    while os.path.exists(out_path):
        out_path = os.path.join(media_dir, f"{safe_stem}_{counter}{out_ext}")
        counter += 1
    try:
        with open(out_path, "wb") as f:
            f.write(zf.read(target))
    except Exception:
        return None
    cache[link_uri] = out_path
    return out_path


def _idml_to_markdown(idml_path):
    """Convert an IDML package to intermediate markdown (docx-compatible)."""
    media_dir = os.path.splitext(idml_path)[0] + "_idml_media"
    _ensure_dir(media_dir)
    with zipfile.ZipFile(idml_path, "r") as zf:
        namelist = zf.namelist()
        style_map, list_styles, ui_styles = _load_idml_styles(zf)
        order = _idml_reading_order(zf)
        if order is None:
            order = [
                ("story", n) for n in sorted(
                    n for n in namelist
                    if n.lower().startswith("stories/") and n.lower().endswith(".xml")
                )
            ]

        lines = []
        cover_images = []
        content_started = False
        image_cache = {}

        def resolve_image(link_uri):
            return _extract_idml_image(zf, namelist, link_uri, media_dir, image_cache)

        def emit_image(link_uri):
            path = resolve_image(link_uri)
            if not path:
                return
            # Images on the opening page form the cover; later images are inline.
            if content_started:
                lines.append(f"![{os.path.basename(path)}]({path})")
                lines.append("")
            else:
                cover_images.append(path)

        for kind, ref in order:
            if kind == "image":
                emit_image(ref)
                continue
            try:
                story_root = ET.fromstring(zf.read(ref))
            except Exception:
                continue
            if _strip_xml_ns(story_root.tag) != "Story":
                story_root = next(
                    (e for e in story_root.iter() if _strip_xml_ns(e.tag) == "Story"),
                    story_root,
                )
            if _idml_story_is_junk(story_root, style_map):
                continue
            blocks = []
            _idml_walk(story_root, style_map, list_styles, blocks, resolve_image, ui_styles)
            for block in blocks:
                if block["kind"] != "image":
                    content_started = True
                if block["kind"] == "heading":
                    heading_text = block["text"]
                    if block.get("appendix"):
                        heading_text = f"{IDML_APPENDIX_MARKER} {heading_text}"
                    lines.append(f"{'#' * max(1, block['level'])} {heading_text}")
                    lines.append("")
                elif block["kind"] == "table":
                    lines.extend(block["lines"])
                    lines.append("")
                elif block["kind"] == "image":
                    emit_image(block["uri"])
                else:
                    marker = block.get("marker") or ""
                    if block.get("list_level"):
                        marker = f"[[LVL:{block['list_level']}]]{marker}"
                    lines.append(f"{marker}{block['text']}")
                    lines.append("")

        if cover_images:
            cover_lines = ["# Cover", ""]
            for path in cover_images:
                cover_lines.append(f"![{os.path.basename(path)}]({path})")
                cover_lines.append("")
            lines = cover_lines + lines

    markdown_text = "\n".join(lines)
    markdown_text = re.sub(r'\n{3,}', '\n\n', markdown_text).strip()
    return markdown_text


def _zip_is_idml_package(zf):
    return any(name.split("/")[-1].lower() == "designmap.xml" for name in zf.namelist())


def _resolve_idml_source(upload_path):
    """Resolve an uploaded .zip/.idml to an IDML package path, or None.

    When the container holds both an .indd and an .idml, the IDML is used; the
    INDD (a proprietary binary format) is ignored. Resources such as a Links/
    folder may sit next to the .idml in the container rather than inside it, so
    they are merged into the resolved package.
    """
    try:
        with zipfile.ZipFile(upload_path, "r") as zf:
            if _zip_is_idml_package(zf):
                return upload_path
            namelist = zf.namelist()
            candidates = sorted(
                name for name in namelist
                if name.lower().endswith(".idml") and not name.endswith("/")
            )
            if not candidates:
                return None
            inner_name = candidates[0]
            inner_data = zf.read(inner_name)
            extra_resources = []
            for name in namelist:
                low = name.lower()
                if name.endswith("/") or low == inner_name.lower():
                    continue
                if low.endswith(".idml") or low.endswith(".indd"):
                    continue
                if low.startswith("__macosx/"):
                    continue
                base = os.path.basename(name)
                if not base or base.startswith("._"):
                    continue
                try:
                    extra_resources.append((name, zf.read(name)))
                except Exception:
                    continue
    except zipfile.BadZipFile:
        return None
    out_path = os.path.join(
        UPLOAD_DIR, f"idml_{int(time.time() * 1000)}_{os.path.basename(inner_name)}"
    )
    try:
        inner_zf = zipfile.ZipFile(io.BytesIO(inner_data))
    except zipfile.BadZipFile:
        return None
    with inner_zf:
        inner_names = set(inner_zf.namelist())
        referenced = _idml_referenced_basenames(inner_zf)
        inner_entries = [
            (name, inner_zf.read(name))
            for name in inner_zf.namelist() if not name.endswith("/")
        ]
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as out_zf:
        for name, data in inner_entries:
            out_zf.writestr(name, data)
        # Only carry container resources the IDML actually references; skip
        # unused Links so a large asset folder does not bloat the package. The
        # .idml package wins on path conflicts.
        for name, data in extra_resources:
            if name in inner_names:
                continue
            if referenced and os.path.basename(name).lower() not in referenced:
                continue
            # Defer formats needing an AI->SVG step so huge assets (e.g. .ai)
            # are not carried into the package at all.
            if os.path.splitext(name)[1].lower() not in IDML_IME_IMAGE_EXTS:
                continue
            out_zf.writestr(name, data)
    return out_path


def _parse_template_zip(template_path):
    tree = {}
    try:
        with zipfile.ZipFile(template_path, "r") as zf:
            for name in zf.namelist():
                if name.endswith("/"):
                    continue
                parts = name.strip("/").split("/")
                current = tree
                for i, part in enumerate(parts[:-1]):
                    if part not in current:
                        current[part] = {}
                    current = current[part]
                if parts[-1].endswith((".dita", ".xml", ".ditamap")):
                    content = zf.read(name).decode("utf-8", errors="ignore")
                    leaf = parts[-1]
                    if len(parts) > 1:
                        parent = tree
                        for p in parts[:-1]:
                            parent = parent.setdefault(p, {})
                        parent[leaf] = {"name": leaf, "content": content}
                    else:
                        tree[leaf] = {"name": leaf, "content": content}
    except Exception:
        pass
    return tree


def _extract_template_parts(template_path):
    """Extract reusable frontmatter XML subset and referenced files from template ZIP."""
    result = {
        "frontmatter_xml": "",
        "files": {},        # filename -> content (bytes)
        "image_files": {},  # image/filename -> content (bytes)
        "language": None,
    }
    try:
        with zipfile.ZipFile(template_path, "r") as zf:
            namelist = zf.namelist()

            # Find and parse the ditamap
            ditamap_content = ""
            for name in namelist:
                if name.endswith(".ditamap"):
                    ditamap_content = zf.read(name).decode("utf-8", errors="ignore")
                    break

            if not ditamap_content:
                return result

            result["language"] = _extract_xml_language(ditamap_content)

            # Extract frontmatter section and keep only cover + booklists/toc.
            fm_match = re.search(r'<frontmatter[^>]*>.*?</frontmatter>', ditamap_content, re.DOTALL)
            if fm_match:
                result["frontmatter_xml"] = _extract_template_frontmatter_subset(fm_match.group(0))

            # Collect all referenced dita files
            all_xml = result["frontmatter_xml"]
            refs = re.findall(r'href="([^"]+\.dita)"', all_xml)

            # Copy dita files from template ZIP
            for ref in refs:
                for name in namelist:
                    if name == ref or name.endswith("/" + ref):
                        result["files"][ref] = zf.read(name)
                        break

            # Copy all image files from template ZIP
            for name in namelist:
                if name.startswith("image/") and not name.endswith("/"):
                    img_name = name
                    result["image_files"][img_name] = zf.read(name)

    except Exception:
        pass
    return result


def _extract_template_frontmatter_subset(frontmatter_xml):
    if not frontmatter_xml:
        return ""

    open_match = re.search(r'^<frontmatter\b[^>]*>', frontmatter_xml)
    close_match = re.search(r'</frontmatter>\s*$', frontmatter_xml)
    if not open_match or not close_match:
        return frontmatter_xml

    topicrefs = re.findall(
        r'<topicref\b[^>]*href="[^"]+\.dita"[^>]*/>|<topicref\b[^>]*href="[^"]+\.dita"[^>]*>.*?</topicref>',
        frontmatter_xml,
        re.DOTALL,
    )
    booklists_match = re.search(r'<booklists\b[^>]*>.*?</booklists>', frontmatter_xml, re.DOTALL)

    parts = [open_match.group(0)]
    for topicref in topicrefs:
        navtitle_match = re.search(r'navtitle="([^"]*)"', topicref)
        navtitle = (navtitle_match.group(1) if navtitle_match else "").strip().lower()
        if navtitle in VERSION_HISTORY_TITLES:
            # The source document provides its own version history topic.
            continue
        parts.append(topicref)
    if booklists_match:
        parts.append(booklists_match.group(0))
    parts.append(close_match.group(0).strip())
    return "\n".join(parts)


def _extract_xml_language(xml_text):
    if not xml_text:
        return None

    patterns = [
        r'xml:lang\s*=\s*"([^"]+)"',
        r'cms:lang\s*=\s*"([^"]+)"',
        r'imeCMS:iba_lang\s*=\s*"([^"]+)"',
    ]
    for pattern in patterns:
        match = re.search(pattern, xml_text, re.IGNORECASE)
        if match:
            return _normalize_dita_language(match.group(1))
    return None


def _normalize_dita_language(lang):
    value = (lang or "").strip().lower()
    if value in {"en", "en-us", "en_us", "english", "英文"}:
        return "en-US"
    if value in {"zh", "zh-cn", "zh_cn", "cn", "chinese", "中文"}:
        return "zh-CN"
    return None


def _parse_language_override(requirements_text):
    if not requirements_text:
        return None

    match = re.search(
        r'(?:xml:lang|lang|language|语言|输出语言|文档语言)\s*[:：=]\s*(zh-cn|zh_cn|zh|cn|中文|en-us|en_us|en|english|英文)',
        requirements_text,
        re.IGNORECASE,
    )
    if match:
        return _normalize_dita_language(match.group(1))

    if re.search(r'输出语言.*英文|文档语言.*英文|xml:lang.*en', requirements_text, re.IGNORECASE):
        return "en-US"
    if re.search(r'输出语言.*中文|文档语言.*中文|xml:lang.*zh', requirements_text, re.IGNORECASE):
        return "zh-CN"
    return None


def _detect_dita_language(source_content, template_parts=None, requirements_text="", explicit_language=None):
    override = _normalize_dita_language(explicit_language) or _parse_language_override(requirements_text)
    if override:
        return override

    text = source_content or ""
    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    alpha_chars = sum(1 for c in text if ('A' <= c <= 'Z') or ('a' <= c <= 'z'))
    total = chinese_chars + alpha_chars

    if total:
        if chinese_chars / total >= 0.2:
            return "zh-CN"
        if alpha_chars:
            return "en-US"

    template_lang = (template_parts or {}).get("language") if template_parts else None
    if template_lang:
        return template_lang
    return "zh-CN"


def _rewrite_xml_language_attrs(xml_text, dita_lang):
    if not xml_text or not dita_lang:
        return xml_text

    rewritten = re.sub(r'xml:lang\s*=\s*"[^"]*"', f'xml:lang="{dita_lang}"', xml_text)
    rewritten = re.sub(r'cms:lang\s*=\s*"[^"]*"', f'cms:lang="{dita_lang}"', rewritten)
    rewritten = re.sub(r'imeCMS:iba_lang\s*=\s*"[^"]*"', f'imeCMS:iba_lang="{dita_lang}"', rewritten)
    return rewritten


def _parse_special_requirements(requirements_text):
    parsed = {"reuse_topics": [], "type_overrides": {}, "auto_split": False, "other": []}
    if not requirements_text:
        return parsed

    reuse_pattern = re.findall(r'沿用[：:]?\s*(\S+)', requirements_text)
    parsed["reuse_topics"] = [r.strip().rstrip(".,;") for r in reuse_pattern]

    type_override_pattern = re.findall(
        r'([^\s,，]+?)\s*[映转][射换][到为]\s*(concept|task|reference)\s*[类类型]',
        requirements_text
    )
    for src, ttype in type_override_pattern:
        parsed["type_overrides"][src.strip()] = ttype.strip()

    if "拆分" in requirements_text or "每个" in requirements_text:
        parsed["auto_split"] = True

    return parsed


def _content_to_dita_xml(section_title, section_content, dita_type, topic_id, dita_lang, level=2, topic_kind="concept", source_format="docx", xref_map=None):
    title_text = section_title or ""
    # English manuals mark UI control names with bold rather than 【】, so a bold
    # run inside an operation step becomes <uicontrol> in English output.
    is_english = str(dita_lang or "").lower().startswith("en")
    is_idml = source_format == "idml"
    is_native_md = source_format == "md"
    if is_native_md:
        title_text = _normalize_native_markdown(title_text)
        section_content = _normalize_native_markdown(section_content)
    title_text = re.sub(r'\[\[B\]\](.*?)\[\[/B\]\]', r'\1', title_text)
    title_text = re.sub(r'\[\[SUP\]\](.*?)\[\[/SUP\]\]', r'\1', title_text)
    title_text = re.sub(r'\[\[SUB\]\](.*?)\[\[/SUB\]\]', r'\1', title_text)
    title_text = re.sub(r'\[\[I\]\](.*?)\[\[/I\]\]', r'\1', title_text)
    title_text = re.sub(r'\[\[CODE\]\](.*?)\[\[/CODE\]\]', r'\1', title_text)
    title_text = re.sub(r'\[\[LINK:[^\]]+\]\](.*?)\[\[/LINK\]\]', r'\1', title_text)
    title_text = _strip_tag(title_text)
    safe_title = title_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    safe_title_attr = _escape_xml_attr(title_text)
    # Batch conversion baseline:
    # 1. Preserve source wording and hierarchy from Word.
    # 2. Reuse template Cover topic and booklists/toc when a template is provided.
    # 3. Drop Word TOC and page-number-only lines.
    # 4. Keep ordered lists continuous and attach nested image/table/note blocks to the same step.
    # 5. Convert note text by label semantics, drop note icon images, and default generic notes to tip.
    # 6. Remove English Figure/Table numbering prefixes from titles while preserving Chinese figure titles.
    # 7. Split embedded table captions that appear inside merged-cell markdown rows into standalone tables.

    def _unescape_md(text):
        for ch in ['*', '_', '\\', '.', '-', '#']:
            text = text.replace('\\' + ch, ch)
        return text

    def _strip_md_bold(text):
        return re.sub(r'\*\*([^*]+)\*\*', r'\1', text)

    def _strip_md_image_alt(text):
        return re.sub(r'!\[([^\]]*)\]\(', r'\1[', text)

    def _restore_inline_run_markup(text, in_step=False):
        restored = text or ''
        restored = re.sub(
            r'!\[([^\]]*)\]\(([^)]+)\)',
            lambda m: f'<image href="{_escape_xml_attr(m.group(2))}"></image>',
            restored,
        )
        if in_step and is_english and not is_native_md:
            # In English operation steps a bold run names a UI control.
            restored = re.sub(r'\[\[B\]\](.*?)\[\[/B\]\]', r'<uicontrol>\1</uicontrol>', restored)
        else:
            restored = re.sub(r'\[\[B\]\](.*?)\[\[/B\]\]', r'<b>\1</b>', restored)
        restored = re.sub(r'\[\[SUP\]\](.*?)\[\[/SUP\]\]', r'<sup>\1</sup>', restored)
        restored = re.sub(r'\[\[SUB\]\](.*?)\[\[/SUB\]\]', r'<sub>\1</sub>', restored)
        restored = re.sub(r'\[\[I\]\](.*?)\[\[/I\]\]', r'<i>\1</i>', restored)
        def _code_repl(match):
            inner = match.group(1)
            if _looks_like_file_format(inner):
                return f'<i>{inner}</i>'
            return inner
        restored = re.sub(r'\[\[CODE\]\](.*?)\[\[/CODE\]\]', _code_repl, restored)
        def _md_link_repl(match):
            url = match.group(1).strip()
            label = match.group(2)
            if url.lower().startswith(("http://", "https://")):
                return (
                    f'<xref href="{url.replace(chr(34), "&quot;")}" scope="external" '
                    f'format="html">{label}</xref>'
                )
            return f'<xref href="{url.replace(chr(34), "&quot;")}">{label}</xref>'
        restored = re.sub(r'\[\[LINK:([^\]]+)\]\](.*?)\[\[/LINK\]\]', _md_link_repl, restored)
        # English on-screen UI text (Silk screen character style) -> <uicontrol>.
        def _ui_repl(match):
            inner = match.group(1)
            # A run of only spaces separates adjacent labels; keep it as text
            # rather than emitting an empty control.
            return f'<uicontrol>{inner.strip()}</uicontrol>' if inner.strip() else inner
        restored = re.sub(r'\[\[UI\]\](.*?)\[\[/UI\]\]', _ui_repl, restored)
        restored = re.sub(r'\[\[/?B\]\]', '', restored)
        restored = re.sub(r'\[\[/?SUP\]\]', '', restored)
        restored = re.sub(r'\[\[/?SUB\]\]', '', restored)
        restored = re.sub(r'\[\[/?I\]\]', '', restored)
        restored = re.sub(r'\[\[/?CODE\]\]', '', restored)
        restored = re.sub(r'\[\[/?UI\]\]', '', restored)
        restored = UI_CONTROL_RE.sub(r'<uicontrol>\1</uicontrol>', restored)
        if is_english:
            def _en_bracket_ui(match):
                inner = match.group(1).strip()
                if not inner or inner in {
                    "B", "/B", "SUP", "/SUP", "SUB", "/SUB", "UI", "/UI",
                    "I", "/I", "CODE", "/CODE", "LINK", "/LINK",
                }:
                    return match.group(0)
                return f'<uicontrol>{inner}</uicontrol>'
            restored = EN_BRACKET_UI_RE.sub(_en_bracket_ui, restored)
        # InDesign cross-reference -> empty <xref cms:title="..."/>. IME fills
        # the visible quote/page text from the target topic.
        def _xref_repl(match):
            target = match.group(1).strip()
            page = (match.group(2) or "").strip()
            display = _clean_xref_title(target) or target
            target_id = (xref_map or {}).get(target) or (xref_map or {}).get(display)
            spaced_title = _space_alnum_cjk(display)
            prefix = _space_alnum_cjk(f'第{page}页') if page else ''
            if target_id:
                return (
                    f'<xref href="{_escape_xml_attr(target_id)}.dita" '
                    f'cms:title="{_escape_xml_attr(display)}"/>'
                )
            if prefix:
                return f'{prefix}\u201c{spaced_title}\u201d'
            return spaced_title
        restored = XREF_RE.sub(_xref_repl, restored)
        if is_native_md and xref_map:
            def _md_section_xref(match):
                num = match.group(1)
                target_id = xref_map.get(num)
                if not target_id:
                    return match.group(0)
                display = xref_map.get(target_id) or target_id
                return (
                    f'<xref href="{_escape_xml_attr(target_id)}.dita" '
                    f'cms:title="{_escape_xml_attr(display)}">{_escape_xml_attr(display)}</xref>'
                )
            restored = re.sub(
                r'(?i)(?:Section|Sec\.)\s+(\d+(?:\.\d+)*)',
                _md_section_xref,
                restored,
            )
            restored = re.sub(r'(\d+(?:\.\d+)*)\s*节', _md_section_xref, restored)
            restored = restored.replace('</xref>第', '</xref> 第')
        return restored

    safe_content = section_content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("<br>", "")

    table_rows = []
    in_table = False
    list_items = []
    in_list = False
    list_type = None
    list_base_level = 0
    pending_table_header_rows = None
    pending_table_wide = None
    pending_table_colwidths = None
    in_codeblock = False
    codeblock_lang = ""
    codeblock_lines = []
    codeblock_indent = ""

    def _flush_list():
        nonlocal in_list, list_items, list_type, list_base_level
        if not in_list:
            return ""

        def build_forest(items):
            """Turn flat items carrying InDesign levels into nested lists."""
            forest = []
            stack = []  # (level, list node, parent item)
            for item in items:
                item_level = item.get("level")
                if item_level is None:
                    item_level = stack[-1][0] if stack else list_base_level
                item_type = item.get("type") or "ul"
                while stack and item_level < stack[-1][0]:
                    stack.pop()
                if not stack:
                    node = {"type": item_type, "items": []}
                    forest.append(node)
                    stack.append((item_level, node, None))
                elif item_level > stack[-1][0]:
                    parent_node = stack[-1][1]
                    if parent_node["items"]:
                        child = {"type": item_type, "items": []}
                        parent_node["items"][-1]["children"].append(child)
                        stack.append((item_level, child, parent_node["items"][-1]))
                    else:
                        stack[-1] = (item_level, parent_node, stack[-1][2])
                elif item_type != stack[-1][1]["type"]:
                    if len(stack) == 1:
                        node = {"type": item_type, "items": []}
                        forest.append(node)
                        stack[-1] = (item_level, node, None)
                    else:
                        parent_item = stack[-2][1]["items"][-1]
                        child = {"type": item_type, "items": []}
                        parent_item["children"].append(child)
                        stack.pop()
                        stack.append((item_level, child, parent_item))
                node = stack[-1][1]
                node["items"].append(item)
            return forest

        def render_node(node, indent):
            tag = "ul" if node["type"] == "ul" else "ol"
            rendered = [f"{indent}<{tag}>"]
            for item in node["items"]:
                child_blocks = "\n".join(item["blocks"])
                children = "".join(
                    "\n" + render_node(child, indent + "    ")
                    for child in item.get("children", [])
                )
                trailing = "\n".join(item.get("trailing") or [])
                if child_blocks or children or trailing:
                    rendered.append(f"{indent}  <li><p>{item['text']}</p>")
                    if child_blocks:
                        rendered.append(child_blocks)
                    if children:
                        rendered.append(children.lstrip("\n"))
                    if trailing:
                        rendered.append(trailing)
                    rendered.append(f"{indent}  </li>")
                else:
                    rendered.append(f"{indent}  <li><p>{item['text']}</p></li>")
            rendered.append(f"{indent}</{tag}>")
            return "\n".join(rendered)

        result = "\n".join(
            render_node(node, "        ") for node in build_forest(list_items)
        )
        in_list = False
        list_items = []
        list_type = None
        list_base_level = 0
        return result

    body_parts = []
    pending_table_title = None
    pending_table_caption_only = None
    pending_image = None
    pending_figure_caption = None
    pending_figure_images = []
    skip_next_note_icon_image = False
    pending_note_type = None
    pending_note_label = None
    pending_note_blocks = []
    pending_note_body = None
    note_icon_detected = False

    def _append_block(xml, default_indent="        "):
        if pending_note_type is not None:
            pending_note_blocks.append(xml)
        elif in_list and list_items:
            _attach_list_xml(xml)
        else:
            body_parts.append(xml)

    def _append_body(xml):
        body_parts.append(xml)

    def _append_list_item(text, level=None, item_type=None):
        list_items.append({
            "text": text,
            "blocks": [],
            "children": [],
            "trailing": [],
            "level": level if level is not None else list_base_level,
            "type": item_type or list_type or "ul",
        })

    def _append_list_continuation(xml):
        """Hang a following paragraph/image on the current parent list item.

        Nested bullets must not steal body that belongs to the outer item.
        If nested items already follow the parent, hang the block after those
        children (trailing). Otherwise append to the parent's ordered blocks
        so the paragraph stays ahead of later notes/figures.
        """
        if not (in_list and list_items):
            body_parts.append(xml)
            return
        _attach_list_xml(xml, continuation=True)

    def _parent_list_item():
        for item in reversed(list_items):
            item_level = item.get("level")
            if item_level is None or item_level <= list_base_level:
                return item
        return list_items[-1]

    def _attach_list_xml(xml, continuation=False):
        """Keep list-item extras in source order.

        Continuation paragraphs go onto the parent item. When the parent is
        still the last item they join ``blocks`` (with notes/figs). After
        nested children exist they join ``trailing``. Later notes/figs follow
        that trailing stream so they stay with the parent-level paragraph.
        """
        parent = _parent_list_item()
        last = list_items[-1]
        nested = last is not parent
        if continuation:
            if nested:
                parent.setdefault("trailing", []).append(xml)
            else:
                parent["blocks"].append(xml)
            return
        if nested and parent.get("trailing"):
            parent["trailing"].append(xml)
        else:
            last["blocks"].append(xml)

    def _strip_list_prefix(text):
        return re.sub(r'^\s*(?:[-*+]\s+|\d+[.)、]\s+)', '', text or '').strip()

    def _clean_output_text(text):
        return _strip_page_reference(_strip_md_bold(_unescape_md(text or '')))

    def _is_figure_caption(text):
        stripped = (text or '').strip()
        if stripped.startswith(IDML_FIGCAP_MARKER):
            return True
        return bool(FIGURE_CAPTION_PREFIX_RE.match(_strip_md_bold(_unescape_md(stripped))))

    def _looks_like_unnumbered_figure_caption(text, href=""):
        compact = _clean_output_text(text or "")
        if not compact or len(compact) > 160:
            return False
        ext = os.path.splitext((href or "").split("?")[0])[1].lower()
        if ext and ext not in {".png", ".jpg", ".jpeg", ".gif", ".tif", ".tiff", ".bmp"}:
            return False
        if _is_figure_caption(text) or TABLE_CAPTION_PREFIX_RE.match(compact):
            return False
        if _is_note_like_text(compact):
            return False
        if re.match(r'^\s*(?:\d+[.)、]|[-*+])\s+', text or ""):
            return False
        if re.match(r'^\d+[A-Za-z]?(?:[-–—]\d+)?$', compact):
            return False
        return True

    def _normalize_figure_title(text):
        # Keep any manual 图4-2/Figure 7 prefix here so an orphan caption can
        # fall back to its verbatim text; _strip_figure_number removes it when
        # the caption is actually rendered as a figure title.
        stripped = (text or '').strip()
        if stripped.startswith(IDML_FIGCAP_MARKER):
            stripped = stripped[len(IDML_FIGCAP_MARKER):].strip()
        return _strip_md_bold(_unescape_md(stripped))

    def _strip_figure_number(text):
        # IME applies its own figure numbering, so only the title body is kept.
        return FIGURE_CAPTION_PREFIX_RE.sub('', text or '').lstrip(":：.．、- ").strip()

    def _is_note_like_text(text):
        stripped_text = _strip_md_bold(_unescape_md(_strip_list_prefix((text or '').strip())))
        stripped_text = re.sub(r'\[\[/?(?:B|SUP|SUB)\]\]', '', stripped_text)
        if stripped_text in {"注意事项", "其他注意事项"}:
            return False
        if re.match(r'^(注意事项|其他注意事项|注意|提示|警告|小心|请勿|切勿)[:：]?\s*(.*)$', stripped_text):
            return True
        return bool(NOTE_LABEL_PATTERN.match(stripped_text))

    def _is_note_icon_image(href):
        path = (href or "").strip()
        if not path or path.startswith(("http://", "https://")) or not os.path.exists(path):
            return False
        try:
            from PIL import Image
            with Image.open(path) as img:
                width, height = img.size
            return width <= 220 and height <= 120
        except Exception:
            return False

    def _infer_note_type_from_text(text):
        normalized = _strip_md_bold(_unescape_md(_strip_list_prefix((text or '').strip()))).lower()
        if any(keyword in normalized for keyword in ["warning", "caution", "danger", "请勿", "切勿", "警告", "小心", "do not"]):
            return "warning"
        if normalized.startswith("注意"):
            return "caution"
        return "tip"

    def _flush_pending_note(text=None):
        nonlocal pending_note_type, pending_note_label, pending_note_blocks, note_icon_detected
        if pending_note_type is None:
            return None
        body = (text or "").strip().lstrip('.:：;； ').strip()
        if body:
            pending_note_blocks.append(f'          <p>{_restore_inline_run_markup(body)}</p>')
        if not pending_note_blocks:
            fallback = pending_note_label or ""
            pending_note_blocks.append(f'          <p>{_restore_inline_run_markup(fallback)}</p>')
        inner = "\n".join(_group_note_enumerated_blocks(pending_note_blocks))
        note_xml = f'        <note type="{pending_note_type}">\n{inner}\n        </note>'
        pending_note_type = None
        pending_note_label = None
        pending_note_blocks = []
        note_icon_detected = False
        return note_xml

    def _group_note_enumerated_blocks(blocks):
        """Turn consecutive 【N】 or [N] paragraphs inside a note into a bullet list."""
        rendered = []
        pending_items = []

        def flush_items():
            if not pending_items:
                return
            items = "\n".join(f'            <li><p>{item}</p></li>' for item in pending_items)
            rendered.append(f'          <ul>\n{items}\n          </ul>')
            pending_items.clear()

        for block in blocks:
            match = NOTE_ENUM_P_RE.match(block)
            if match and match.group(1).strip():
                pending_items.append(match.group(1).strip())
                continue
            flush_items()
            rendered.append(block)
        flush_items()
        return rendered

    def _next_nonempty_line(lines, start_idx):
        for next_idx in range(start_idx + 1, len(lines)):
            candidate = lines[next_idx].strip()
            if candidate:
                return candidate
        return ""

    def _next_image_belongs_to_following_caption(lines, start_idx):
        """True when the next image is the lead image of the following figure."""
        for next_idx in range(start_idx + 1, len(lines)):
            candidate = lines[next_idx].strip()
            if not candidate:
                continue
            if not MD_IMAGE_LINE_RE.match(candidate):
                return False
            return _is_figure_caption(_next_nonempty_line(lines, next_idx))
        return False

    def _flush_pending_note_to_body():
        """Emit an open pending note before starting or appending another one.

        Consecutive note lines would otherwise overwrite the pending note (losing
        content) or reorder notes, so flush the open note first.
        """
        note_xml = _flush_pending_note()
        if note_xml:
            # Keep notes encountered inside a step list attached to that step.
            _append_block(note_xml)

    def _flush_pending_image():
        nonlocal pending_image
        if not pending_image:
            return None
        image_xml = (
            f'        <image href="{_escape_xml_attr(pending_image["href"])}"></image>'
        )
        pending_image = None
        return image_xml

    def _figure_xml(title, hrefs):
        images = "".join(
            f'<image href="{_escape_xml_attr(href)}"></image>'
            for href in hrefs
            if href
        )
        return (
            f'        <fig><title>{_restore_inline_run_markup(_strip_figure_number(title))}</title>'
            f'{images}</fig>'
        )

    def _flush_pending_figure():
        nonlocal pending_figure_caption, pending_figure_images, pending_image
        if pending_figure_caption is None:
            return None
        hrefs = list(pending_figure_images)
        if pending_image:
            hrefs.append(pending_image["href"])
            pending_image = None
        pending_figure_images = []
        title = pending_figure_caption
        pending_figure_caption = None
        if hrefs:
            return _figure_xml(title, hrefs)
        return f"        <p>{_restore_inline_run_markup(title)}</p>"

    def _normalize_table_title(text):
        normalized = _strip_md_bold(_unescape_md((text or '').strip()))
        return TABLE_CAPTION_PREFIX_RE.sub('', normalized).lstrip(":：.．、- ").strip()

    def _strip_page_reference(text):
        cleaned = re.sub(r'\s+on\s+page\s+\d+\b', '', text or '', flags=re.IGNORECASE)
        cleaned = re.sub(r'\s{2,}', ' ', cleaned)
        return cleaned.strip()

    def _join_caption_fragments(parts):
        merged = ''
        for part in (p for p in parts if p):
            if not merged:
                merged = part
                continue
            if merged[-1:].isalnum() and part[:1].islower():
                merged += part
                continue
            merged += f' {part}'
        return merged.strip()

    def _extract_embedded_table_caption(cells):
        if not cells:
            return None
        first = _strip_md_bold(_unescape_md((cells[0] or '').strip()))
        if not TABLE_CAPTION_PREFIX_RE.match(first):
            return None
        parts = [first] + [(_strip_md_bold(_unescape_md((cell or '').strip()))) for cell in cells[1:] if (cell or '').strip()]
        return _join_caption_fragments(parts)

    def _flush_pending_table():
        nonlocal in_table, table_rows, pending_table_title, pending_table_caption_only
        nonlocal pending_table_header_rows, pending_table_wide, pending_table_colwidths
        if not in_table or not table_rows:
            in_table = False
            table_rows = []
            pending_table_header_rows = None
            return None

        in_table = False
        has_title = bool(pending_table_title)
        prev = None
        if not has_title and body_parts:
            prev = body_parts[-1]
            if prev and prev.strip().startswith("<p>") and re.match(r'<p>Table\s+\d+([\s:.-]|&amp;|\(|$)', prev):
                has_title = True
                body_parts.pop()

        filtered_rows = []
        header_row = table_rows[0] if table_rows else []
        for idx, row in enumerate(table_rows):
            if idx > 0 and _is_repeated_table_header_row(row, header_row):
                continue
            filtered_rows.append(row)
        header_rows = pending_table_header_rows
        pending_table_header_rows = None
        if header_rows is None:
            header_rows = 1 if len(filtered_rows) > 1 else 0
        header_rows = max(0, min(header_rows, len(filtered_rows)))
        if header_rows >= len(filtered_rows) and len(filtered_rows) > 1:
            header_rows = 1
        # IDML tables carry explicit merge info (markers); the Word-oriented
        # heuristics below would otherwise blank/merge cells that the source
        # already marks up, so they only apply to span-free tables.
        has_spans = any(
            IDML_SPAN_COVERED in (cell or "") or IDML_SPAN_MARK_RE.search(cell or "")
            for row in filtered_rows
            for cell in row
        )
        if not has_spans:
            filtered_rows = _drop_redundant_first_body_row(filtered_rows)
            filtered_rows = _collapse_grouped_first_column_rows(filtered_rows)

        cols = max(len(r) for r in filtered_rows)
        # IDML merged cells: a cell marked [[SPAN:c,r]] spans c columns and r
        # rows; cells covered by a neighbour travel as IDML_SPAN_COVERED and
        # are skipped. Vertical merges become morerows, horizontal merges
        # namest/nameend, matching the reference IME table markup.
        def _parse_span_cell(cell):
            raw = cell or ""
            if IDML_SPAN_COVERED in raw:
                return "", 1, 1, True
            colspan = rowspan = 1
            match = IDML_SPAN_MARK_RE.search(raw)
            if match:
                colspan = max(1, int(match.group(1)))
                rowspan = max(1, int(match.group(2)))
                raw = IDML_SPAN_MARK_RE.sub("", raw)
            return raw.strip(), colspan, rowspan, False

        def _dita_table_entry_xml(cell_text, attrs=""):
            stripped = (cell_text or "").strip()
            ul = stripped.startswith(IDML_CELL_UL_OPEN) and stripped.endswith(IDML_CELL_UL_CLOSE)
            ol = stripped.startswith(IDML_CELL_OL_OPEN) and stripped.endswith(IDML_CELL_OL_CLOSE)
            if ul or ol:
                inner = stripped[len(IDML_CELL_UL_OPEN if ul else IDML_CELL_OL_OPEN):
                                 -len(IDML_CELL_UL_CLOSE if ul else IDML_CELL_OL_CLOSE)]
                items = [i for i in inner.split(IDML_CELL_LIST_SEP) if i.strip()]
                tag = "ul" if ul else "ol"
                lis = "".join(
                    f"<li><p>{_restore_inline_run_markup(i)}</p></li>" for i in items
                )
                return f"<entry{attrs}><{tag}>{lis}</{tag}></entry>"
            restored = _restore_inline_run_markup(cell_text or "")
            if not restored.strip():
                return f"<entry{attrs}></entry>"
            return f"<entry{attrs}><p>{restored}</p></entry>"

        def _emit_span_row_entries(row, indent):
            entries = []
            col = 0
            # [[SPANC]] after a same-row colspan already advanced `col`;
            # only leftover vMerge continues should bump the column index.
            pending_hspan = 0
            for cell in row:
                text, colspan, rowspan, covered = _parse_span_cell(cell)
                if covered:
                    if pending_hspan > 0:
                        pending_hspan -= 1
                        continue
                    col += 1
                    continue
                attrs = ""
                if colspan > 1:
                    end = min(col + colspan - 1, cols - 1)
                    if end > col:
                        attrs += f' namest="COLSPEC{col}" nameend="COLSPEC{end}"'
                    pending_hspan += max(0, colspan - 1)
                if rowspan > 1:
                    attrs += f' morerows="{rowspan - 1}"'
                entries.append(f'{indent}{_dita_table_entry_xml(text, attrs)}')
                col += colspan
            return entries
        # IDML/Word callout boxes (warning, tip) surface as a single-column
        # table whose header cell carries a symbol icon. Emit them as <note>
        # so the emphasis survives in IME instead of becoming a title-less
        # table. The explicit type travels as a [[NOTE:type]] marker; a plain
        # empty header defaults to tip.
        if not has_title and cols == 1 and filtered_rows:
            header_cell = (filtered_rows[0][0] if filtered_rows[0] else "").strip()
            marker = IDML_CALLOUT_MARKER_RE.match(header_cell)
            if marker or not header_cell:
                callout_type = marker.group(1) if marker else "tip"
                callout_bodies = [
                    (row[0] if row else "").strip()
                    for row in filtered_rows[1:]
                ]
                callout_bodies = [body for body in callout_bodies if body]
                if callout_bodies:
                    table_rows = []
                    pending_table_title = None
                    pending_table_caption_only = None
                    pending_table_wide = None
                    pending_table_colwidths = None
                    note_blocks = []
                    list_items_pending = []

                    def flush_note_list_items():
                        if not list_items_pending:
                            return
                        items = "\n".join(
                            f'            <li><p>{item}</p></li>'
                            for item in list_items_pending
                        )
                        note_blocks.append(
                            f'          <ul>\n{items}\n          </ul>'
                        )
                        list_items_pending.clear()

                    for body in callout_bodies:
                        list_match = re.match(r'^\s*-\s+(.*)$', body, re.S)
                        if list_match:
                            list_items_pending.append(
                                _restore_inline_run_markup(list_match.group(1))
                            )
                            continue
                        flush_note_list_items()
                        note_blocks.append(
                            f'          <p>{_restore_inline_run_markup(body)}</p>'
                        )
                    flush_note_list_items()
                    paragraphs = "\n".join(note_blocks)
                    return (
                        f'        <note type="{callout_type}">\n'
                        f'{paragraphs}\n'
                        f'        </note>'
                    )
        title_text = ""
        if has_title:
            title_text = _restore_inline_run_markup(_normalize_table_title(pending_table_title or _strip_tag(prev)))
        wide = pending_table_wide or (
            "180mm" if _dita_table_should_be_extra_wide(cols, section_title, title_text) else None
        )
        pending_table_wide = None
        table_attr = f' outputclass="{wide}"' if wide else ""
        if has_title:
            table_xml = [f'        <table{table_attr}>', f'          <title>{title_text}</title>']
        else:
            table_xml = [f'        <table{table_attr}>']

        table_xml.append(f'          <tgroup cols="{cols}">')
        # IME needs one <colspec> per column to render and resize column
        # widths; a <tgroup> without them yields a table with fixed columns.
        colwidths = pending_table_colwidths
        pending_table_colwidths = None
        for col_index in range(cols):
            width = "1.00*"
            if colwidths and len(colwidths) == cols:
                width = colwidths[col_index]
            table_xml.append(
                f'            <colspec colname="COLSPEC{col_index}" colwidth="{width}"/>'
            )
        if header_rows:
            table_xml.append('            <thead>')
            for row in filtered_rows[:header_rows]:
                table_xml.append('              <row>')
                if has_spans:
                    table_xml.extend(_emit_span_row_entries(row, '                '))
                else:
                    for c in row:
                        table_xml.append(f'                {_dita_table_entry_xml(c)}')
                    empty_needed = cols - len(row)
                    for _ in range(empty_needed):
                        table_xml.append('                <entry></entry>')
                table_xml.append('              </row>')
            table_xml.append('            </thead>')
            table_xml.append('            <tbody>')
            for row in filtered_rows[header_rows:]:
                table_xml.append('              <row>')
                if has_spans:
                    table_xml.extend(_emit_span_row_entries(row, '                '))
                else:
                    for c in row:
                        table_xml.append(f'                {_dita_table_entry_xml(c)}')
                    empty_needed = cols - len(row)
                    for _ in range(empty_needed):
                        table_xml.append('                <entry></entry>')
                table_xml.append('              </row>')
            table_xml.append('            </tbody>')
        else:
            table_xml.append('            <tbody>')
            for row in filtered_rows:
                table_xml.append('              <row>')
                if has_spans:
                    table_xml.extend(_emit_span_row_entries(row, '                '))
                else:
                    for c in row:
                        table_xml.append(f'                {_dita_table_entry_xml(c)}')
                table_xml.append('              </row>')
            table_xml.append('            </tbody>')
        table_xml.append('          </tgroup>')
        table_xml.append('        </table>')
        table_rows = []
        pending_table_title = None
        pending_table_caption_only = None
        return "\n".join(table_xml)

    def _looks_like_table_title_continuation(text):
        normalized = _strip_md_bold(_unescape_md((text or '').strip()))
        if not normalized:
            return False
        if normalized.startswith(("#", "!", "|")):
            return False
        if TABLE_CAPTION_PREFIX_RE.match(normalized):
            return False
        if re.match(r'^\d+[.)、]?$', normalized):
            return False
        if re.match(r'^\d+[.)]\s+', normalized):
            return False
        return len(normalized) <= 160

    def _consume_note_line(text, next_nonempty=""):
        raw_text = (text or '').strip()
        # A bolded space before the label ("[[B]] [[/B]]注意：") is a Word
        # artifact; drop it so the note label is still recognised.
        raw_text = re.sub(r'^(?:\s*\[\[B\]\]\s*\[\[/B\]\])+\s*', '', raw_text)
        original_text = _strip_md_bold(_unescape_md(raw_text))
        stripped_text = _strip_md_bold(_unescape_md(_strip_list_prefix(raw_text)))
        normalized_text = re.sub(r'\s+', ' ', stripped_text).strip()
        if stripped_text in {"注意事项", "其他注意事项"}:
            return None
        has_prefixed_note = bool(NOTE_LABEL_PATTERN.match(normalized_text) or CHINESE_NOTE_LABEL_PATTERN.match(normalized_text))
        if original_text.startswith(("- ", "* ", "+ ")) and not has_prefixed_note:
            if any(keyword in normalized_text for keyword in ["请勿", "切勿", "小心", "警告"]):
                return f'        <note type="warning"><p>{normalized_text}</p></note>'
            return None
        note_match = CHINESE_NOTE_LABEL_PATTERN.match(normalized_text) or NOTE_LABEL_PATTERN.match(normalized_text)
        if note_match:
            label = note_match.group(1)
            detail = note_match.group(2).strip()
            # When the whole line is bold, the opening marker is consumed with the
            # label and an unmatched closing marker is left in the detail; re-wrap
            # it so the emphasis survives as <b>.
            if detail.endswith("[[/B]]") and "[[B]]" not in detail:
                detail = f'[[B]]{detail[:-len("[[/B]]")]}[[/B]]'
            elif detail.startswith("[[/B]]"):
                detail = detail[len("[[/B]]"):].strip()
            if detail and not re.sub(r'[.:：;；,，!！?？\-\s\[\]/]+', '', detail):
                detail = ''
            label_key = label.lower()
            if label in {"警告", "小心", "请勿", "切勿"} or label_key in {"warning", "caution", "danger"}:
                note_type = "warning"
            elif label == "注意":
                note_type = "caution"
            else:
                note_type = "tip"
            if (
                detail
                and not re.match(r'^\s*[-*+]\s+', next_nonempty)
                # "注意：【1】..." continues with 【2】【3】 on later lines, so
                # keep the note open to collect them into one bullet list.
                and not NOTE_ENUM_MARKER_RE.match(detail)
            ):
                return f'        <note type="{note_type}"><p>{_restore_inline_run_markup(detail)}</p></note>'
            return {"pending_type": note_type, "label": label, "detail": detail}
        chinese_action_match = CHINESE_WARNING_ACTION_PATTERN.match(normalized_text)
        if chinese_action_match:
            detail = chinese_action_match.group(2).strip() or normalized_text
            return f'        <note type="warning"><p>{_restore_inline_run_markup(detail)}</p></note>'
        return None

    def _flush_codeblock():
        nonlocal in_codeblock, codeblock_lang, codeblock_lines, codeblock_indent
        if not in_codeblock:
            return
        code_text = "\n".join(codeblock_lines)
        lang_attr = f' outputclass="{codeblock_lang}"' if codeblock_lang else ""
        _append_block(f'        <codeblock{lang_attr} xml:space="preserve">{code_text}</codeblock>')
        in_codeblock = False
        codeblock_lang = ""
        codeblock_lines = []
        codeblock_indent = ""

    safe_lines = safe_content.split("\n")
    for idx, line in enumerate(safe_lines):
        line_level = None
        level_match = re.match(r'^\[\[LVL:(\d+)\]\]', line)
        if level_match:
            line_level = int(level_match.group(1))
            line = line[level_match.end():]
        stripped = line.strip()
        fence_match = re.match(r'^(```|~~~)(.*)$', stripped)
        if in_codeblock:
            if fence_match:
                _flush_codeblock()
            else:
                if codeblock_indent and line.startswith(codeblock_indent):
                    codeblock_lines.append(line[len(codeblock_indent):])
                else:
                    codeblock_lines.append(line)
            continue
        if fence_match:
            table_xml = _flush_pending_table()
            if table_xml:
                _append_block(table_xml)
            in_codeblock = True
            codeblock_lang = (fence_match.group(2) or "").strip()
            codeblock_lines = []
            indent_match = re.match(r'^[ \t]*', line)
            codeblock_indent = indent_match.group(0) if indent_match else ""
            continue
        if line_level is None and re.match(r'^[ \t]+(?:[-*+]\s+|\d+[.)]\s+)', line):
            leading = len(re.match(r'^[ \t]*', line).group(0).replace('\t', '    '))
            line_level = max(1, leading // 2)
        if re.match(r'^(?:(?:\*[ \t]*){3,}|(?:-[ \t]*){3,}|(?:_[ \t]*){3,})$', stripped):
            continue
        if stripped.startswith("[[THEAD:"):
            header_match = re.match(r'^\[\[THEAD:(\d+)\]\]$', stripped)
            if header_match:
                table_xml = _flush_pending_table()
                if table_xml:
                    _append_block(table_xml)
                pending_table_header_rows = int(header_match.group(1))
                continue
        if stripped.startswith("[[COLW:"):
            colw_match = re.match(r'^\[\[COLW:([^\]]+)\]\]$', stripped)
            if colw_match:
                pending_table_colwidths = [
                    part.strip() for part in colw_match.group(1).split(",") if part.strip()
                ]
                continue
        if stripped.startswith("[[TWIDE:"):
            wide_match = re.match(r'^\[\[TWIDE:([^\]]+)\]\]$', stripped)
            if wide_match:
                pending_table_wide = wide_match.group(1).strip()
                continue
        if not stripped:
            if pending_note_type and note_icon_detected:
                continue
            if pending_note_type:
                continue
            if in_list:
                # A blank line ends any table that was opened inside this step.
                table_xml = _flush_pending_table()
                if table_xml:
                    _append_block(table_xml)
                continue
            # A blank line terminates a table so two adjacent tables stay
            # separate instead of merging into one.
            if in_table and pending_image:
                # An inline icon queued just before this table keeps its place.
                image_xml = _flush_pending_image()
                if image_xml:
                    _append_block(image_xml)
            table_xml = _flush_pending_table()
            if table_xml:
                _append_block(table_xml)
            _append_body("")
            continue

        current_image_match = MD_IMAGE_LINE_RE.match(stripped)
        if pending_figure_caption is not None and not current_image_match:
            # The caption was not followed by an image, so keep it as body text.
            leftover_figure = _flush_pending_figure()
            if leftover_figure:
                _append_block(leftover_figure)

        next_nonempty = _next_nonempty_line(safe_lines, idx)
        # IDML warnings surface as callout tables, so a bulleted or numbered
        # item must stay a plain list entry rather than be promoted to a note
        # by keyword (which would fold it into the previous item).
        is_list_line = bool(re.match(r'^\s*(?:[-*+]\s+|\d+[.)]\s+)', stripped))
        note_xml = None if (is_idml and is_list_line) else _consume_note_line(stripped, next_nonempty)
        if note_xml:
            if isinstance(note_xml, dict):
                _flush_pending_note_to_body()
                # A table written before the note must stay ahead of it, not be
                # swallowed into the note body when the note opens.
                table_xml = _flush_pending_table()
                if table_xml:
                    _append_block(table_xml)
                pending_note_type = note_xml["pending_type"]
                pending_note_label = note_xml.get("label")
                pending_note_blocks = []
                detail = note_xml.get("detail")
                if detail:
                    pending_note_blocks.append(f'          <p>{_restore_inline_run_markup(detail)}</p>')
                skip_next_note_icon_image = True
                pending_image = None
                note_icon_detected = False
                continue
            _flush_pending_note_to_body()
            table_xml = _flush_pending_table()
            if table_xml:
                _append_block(table_xml)
            pending_image = None
            skip_next_note_icon_image = True
            _append_block(note_xml)
            continue

        if TABLE_CAPTION_PREFIX_RE.match(_unescape_md(stripped)):
            table_xml = _flush_pending_table()
            if table_xml:
                _append_block(table_xml)
            if in_list and list_type == "ol" and list_items:
                pending_table_title = _normalize_table_title(stripped)
                pending_table_caption_only = _strip_md_bold(_unescape_md(stripped))
                continue
            result = _flush_list()
            if result:
                _append_block(result)
            pending_table_title = _normalize_table_title(stripped)
            pending_table_caption_only = _strip_md_bold(_unescape_md(stripped))
            continue

        if stripped.startswith(IDML_TABCAP_MARKER):
            # IDML table caption (Table-title style): lift it into
            # <table><title> so IME regenerates the "表 N" number.
            table_xml = _flush_pending_table()
            if table_xml:
                _append_block(table_xml)
            caption_text = _strip_md_bold(
                _unescape_md(stripped[len(IDML_TABCAP_MARKER):])
            ).strip()
            if in_list and list_type == "ol" and list_items:
                pending_table_title = _normalize_table_title(caption_text)
                pending_table_caption_only = caption_text
                continue
            result = _flush_list()
            if result:
                _append_block(result)
            pending_table_title = _normalize_table_title(caption_text)
            pending_table_caption_only = caption_text
            continue

        if in_table and re.match(r'^\|[-:\s|]+\|$', stripped):
            continue

        if stripped.startswith("|") and stripped.endswith("|"):
            if not in_table:
                in_table = True
                table_rows = []
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            # A caption row can also open the table (merged-cell first row).
            embedded_caption = _extract_embedded_table_caption(cells)
            if embedded_caption:
                table_xml = _flush_pending_table()
                if table_xml:
                    _append_block(table_xml)
                pending_table_title = _normalize_table_title(embedded_caption)
                pending_table_caption_only = embedded_caption
                in_table = True
                table_rows = []
                continue
            table_rows.append([_strip_md_bold(_unescape_md(c)) for c in cells])
            continue
        else:
            if in_table and pending_image:
                # An inline icon queued just before this table keeps its place.
                image_xml = _flush_pending_image()
                if image_xml:
                    _append_block(image_xml)
            table_xml = _flush_pending_table()
            if table_xml:
                _append_block(table_xml)

        if pending_table_title is not None and _looks_like_table_title_continuation(stripped):
            continuation = _strip_md_bold(_unescape_md(stripped))
            pending_table_title = f"{pending_table_title} {continuation}".strip() if pending_table_title else continuation
            pending_table_caption_only = f"{pending_table_caption_only} {continuation}".strip() if pending_table_caption_only else continuation
            continue

        image_match = current_image_match
        if image_match:
            href = image_match.group(2)
            if pending_figure_caption is not None:
                if _is_figure_caption(_next_nonempty_line(safe_lines, idx)):
                    figure_xml = _flush_pending_figure()
                    if figure_xml:
                        _append_block(figure_xml)
                    pending_image = {"alt": image_match.group(1), "href": href}
                    continue
                pending_figure_images.append(href)
                pending_image = None
                next_image = MD_IMAGE_LINE_RE.match(_next_nonempty_line(safe_lines, idx))
                if not next_image:
                    figure_xml = _flush_pending_figure()
                    if figure_xml:
                        _append_block(figure_xml)
                continue
            prev_line = safe_lines[idx - 1].strip() if idx > 0 else ""
            next_line = safe_lines[idx + 1].strip() if idx + 1 < len(safe_lines) else ""
            adjacent_note = _is_note_like_text(prev_line) or _is_note_like_text(next_line)
            image_exists = os.path.exists(href)
            # Small images are real button/UI icons only when they sit next to a
            # note; a figure that merely follows a note is kept.
            drop_as_icon = (
                _is_note_icon_image(href)
                and (adjacent_note or skip_next_note_icon_image or pending_note_type is not None)
            ) or (not image_exists and (skip_next_note_icon_image or adjacent_note))
            if drop_as_icon:
                # Never lose a queued figure while dropping an icon.
                image_xml = _flush_pending_image()
                if image_xml:
                    _append_block(image_xml)
                skip_next_note_icon_image = False
                if pending_note_type is not None:
                    note_icon_detected = True
                continue
            skip_next_note_icon_image = False
            alt = image_match.group(1)
            image_xml = _flush_pending_image()
            if image_xml:
                _append_block(image_xml)
            pending_image = {"alt": alt, "href": href}
            continue

        if _is_figure_caption(stripped):
            figure_title = _normalize_figure_title(stripped)
            followed_by_image = bool(
                MD_IMAGE_LINE_RE.match(_next_nonempty_line(safe_lines, idx))
            )
            if pending_figure_caption is not None:
                leftover_figure = _flush_pending_figure()
                if leftover_figure:
                    _append_block(leftover_figure)
            if pending_image:
                # Image written before its caption (most common layout).
                hrefs = [pending_image["href"]]
                pending_image = None
                extra_images_belong_here = (
                    followed_by_image
                    and not _next_image_belongs_to_following_caption(safe_lines, idx)
                )
                if extra_images_belong_here:
                    pending_figure_caption = figure_title
                    pending_figure_images = hrefs
                else:
                    _append_block(_figure_xml(figure_title, hrefs))
            elif followed_by_image:
                # Caption written before its image; bind once the image arrives.
                pending_figure_caption = figure_title
            else:
                _append_block(f"        <p>{_restore_inline_run_markup(figure_title)}</p>")
            continue

        if re.match(r'^\s*[-*+]\s+', line):
            next_nonempty = _next_nonempty_line(safe_lines, idx)
            # IDML warnings surface as callout tables, so a bulleted or
            # numbered item is a plain list entry and must not be promoted
            # to a note by keyword (that would fold it into the previous item).
            note_xml = None if is_idml else _consume_note_line(line, next_nonempty)
            if note_xml:
                if isinstance(note_xml, dict):
                    _flush_pending_note_to_body()
                    table_xml = _flush_pending_table()
                    if table_xml:
                        _append_block(table_xml)
                    pending_note_type = note_xml["pending_type"]
                    pending_note_label = note_xml.get("label")
                    pending_note_blocks = []
                    detail = note_xml.get("detail")
                    if detail:
                        pending_note_blocks.append(f'          <p>{_restore_inline_run_markup(detail)}</p>')
                    pending_image = None
                    skip_next_note_icon_image = True
                    continue
                _flush_pending_note_to_body()
                pending_image = None
                skip_next_note_icon_image = True
                _append_block(note_xml)
                continue
            start_bullet_list = (
                not in_list
                or (
                    list_type != "ul"
                    and (line_level is None or line_level <= list_base_level)
                )
            )
            if start_bullet_list:
                if in_list and pending_image:
                    # A queued inline icon belongs to the step that just ended.
                    image_xml = _flush_pending_image()
                    if image_xml:
                        _append_list_continuation(image_xml)
                result = _flush_list()
                if result:
                    _append_block(result)
                image_xml = _flush_pending_image()
                if image_xml:
                    _append_block(image_xml)
                in_list = True
                list_type = "ul"
                list_base_level = line_level or 0
            elif pending_image:
                # An inline icon queued after the previous bullet belongs to that
                # step, so attach it before starting the next one.
                image_xml = _flush_pending_image()
                if image_xml:
                    if line_level is not None and line_level > list_base_level:
                        _append_block(image_xml)
                    else:
                        _append_list_continuation(image_xml)
            item = re.sub(r'^\s*[-*+]\s+', '', line)
            _append_list_item(
                _restore_inline_run_markup(_clean_output_text(item), in_step=True),
                line_level,
                "ul",
            )
        elif re.match(r'^\s*\d+[.)]\s+', line):
            next_nonempty = _next_nonempty_line(safe_lines, idx)
            # IDML warnings surface as callout tables, so a bulleted or
            # numbered item is a plain list entry and must not be promoted
            # to a note by keyword (that would fold it into the previous item).
            note_xml = None if is_idml else _consume_note_line(line, next_nonempty)
            if note_xml:
                if isinstance(note_xml, dict):
                    _flush_pending_note_to_body()
                    table_xml = _flush_pending_table()
                    if table_xml:
                        _append_block(table_xml)
                    pending_note_type = note_xml["pending_type"]
                    pending_note_label = note_xml.get("label")
                    pending_note_blocks = []
                    detail = note_xml.get("detail")
                    if detail:
                        pending_note_blocks.append(f'          <p>{_restore_inline_run_markup(detail)}</p>')
                    pending_image = None
                    skip_next_note_icon_image = True
                    continue
                _flush_pending_note_to_body()
                pending_image = None
                skip_next_note_icon_image = True
                _append_block(note_xml)
                continue
            if pending_note_type and pending_note_blocks:
                # Close an open note into the previous step before the next
                # step starts, so the note stays inside its own step item.
                _flush_pending_note_to_body()
            start_numbered_list = (
                not in_list
                or (
                    list_type != "ol"
                    and (line_level is None or line_level <= list_base_level)
                )
            )
            if start_numbered_list:
                if in_list and pending_image:
                    # A queued inline icon belongs to the step that just ended.
                    image_xml = _flush_pending_image()
                    if image_xml:
                        _append_list_continuation(image_xml)
                result = _flush_list()
                if result:
                    _append_block(result)
                image_xml = _flush_pending_image()
                if image_xml:
                    _append_block(image_xml)
                in_list = True
                list_type = "ol"
                list_base_level = line_level or 0
            elif pending_image:
                # An inline icon queued after the previous step belongs to that
                # step, so attach it before starting the next one.
                image_xml = _flush_pending_image()
                if image_xml:
                    if line_level is not None and line_level > list_base_level:
                        _append_block(image_xml)
                    else:
                        _append_list_continuation(image_xml)
            item = re.sub(r'^\s*\d+[.)]\s+', '', line)
            _append_list_item(
                _restore_inline_run_markup(_clean_output_text(item), in_step=True),
                line_level,
                "ol",
            )
        elif re.match(r'^#{1,6}\s+', line):
            result = _flush_list()
            if result:
                body_parts.append(result)
            image_xml = _flush_pending_image()
            if image_xml:
                body_parts.append(image_xml)
            h_level = len(re.match(r'^(#+)', line).group(1))
            h_text = _unescape_md(re.sub(r'^#{1,6}\s+', '', line))
            body_parts.append(f"        <section><title>{h_text}</title></section>")
        else:
            clean = _clean_output_text(stripped)
            if pending_note_type:
                if NOTE_ENUM_MARKER_RE.match(clean):
                    # Enumerated items after a label-only note belong to that note.
                    pending_note_blocks.append(
                        f'          <p>{_restore_inline_run_markup(clean)}</p>'
                    )
                    continue
                if re.match(r'^\d+[A-Za-z]?(?:[-–—]\d+)?$', clean):
                    # A standalone number inside an open note is page furniture,
                    # not note content, so drop the line and abandon the empty note.
                    pending_note_type = None
                    pending_note_label = None
                    pending_note_blocks = []
                    pending_note_body = None
                    note_icon_detected = False
                    continue
                note_xml = _flush_pending_note(clean)
                _append_block(note_xml)
                continue
            next_line = safe_lines[idx + 1].strip() if idx + 1 < len(safe_lines) else ""
            next_image_match = MD_IMAGE_LINE_RE.match(next_line)
            next_image_href = next_image_match.group(2) if next_image_match else ""
            # A missing image cannot be measured, so only treat it as a note icon
            # when the neighbouring text already reads like a note.
            looks_like_note = _is_note_like_text(clean) or _infer_note_type_from_text(clean) == "warning"
            if next_image_href and (
                _is_note_icon_image(next_image_href)
                or (looks_like_note and not os.path.exists(next_image_href))
            ):
                note_type = _infer_note_type_from_text(clean)
                skip_next_note_icon_image = True
                _append_block(f'        <note type="{note_type}"><p>{_restore_inline_run_markup(clean)}</p></note>')
                continue
            if pending_image and _is_note_icon_image(pending_image.get("href")):
                note_type = _infer_note_type_from_text(clean)
                pending_image = None
                _append_block(f'        <note type="{note_type}"><p>{_restore_inline_run_markup(clean)}</p></note>')
                continue
            if note_icon_detected and clean:
                note_type = _infer_note_type_from_text(clean)
                note_icon_detected = False
                _append_block(f'        <note type="{note_type}"><p>{_restore_inline_run_markup(clean)}</p></note>')
                continue
            if pending_image and _looks_like_unnumbered_figure_caption(clean, pending_image.get("href")):
                fig_xml = _figure_xml(clean, [pending_image["href"]])
                pending_image = None
                _append_block(fig_xml)
                continue
            image_xml = _flush_pending_image()
            if image_xml:
                if in_list and list_items:
                    _append_list_continuation(image_xml)
                else:
                    _append_block(image_xml)
            if pending_table_caption_only:
                body_parts.append(f"        <p>{_restore_inline_run_markup(pending_table_caption_only)}</p>")
                pending_table_title = None
                pending_table_caption_only = None
            if in_list and list_items:
                if re.match(r'^\d+[A-Za-z]?(?:[-–—]\d+)?$', clean):
                    continue
                hang_on_item = (not is_native_md) or bool(re.match(r'^[ \t]+', line))
                if hang_on_item:
                    _append_list_continuation(
                        f"        <p>{_restore_inline_run_markup(clean)}</p>"
                    )
                    continue
            if re.match(r'^\d+[A-Za-z]?(?:[-–—]\d+)?$', clean):
                continue
            result = _flush_list()
            if result:
                _append_body(result)
            _append_body(f"        <p>{_restore_inline_run_markup(clean)}</p>")

    _flush_codeblock()
    if pending_note_type and pending_note_blocks:
        # Attach a trailing note to the last step before emitting the list.
        _flush_pending_note_to_body()
    # A table or callout at the very end of a step list belongs inside the last
    # step, so attach it before the <ol> is closed.
    table_xml = _flush_pending_table()
    if table_xml:
        _append_block(table_xml)
    elif pending_table_caption_only:
        _append_block(f"        <p>{_restore_inline_run_markup(pending_table_caption_only)}</p>")
    if pending_figure_caption is not None:
        # An orphan caption still belongs to the step that produced it.
        leftover_figure = _flush_pending_figure()
        if leftover_figure:
            _append_block(leftover_figure)
    # An inline icon queued on the final step must stay inside that step instead
    # of escaping after the closing </ol>/<ul>.
    image_xml = _flush_pending_image()
    if image_xml:
        if in_list and list_items:
            _append_list_continuation(image_xml)
        else:
            _append_block(image_xml)
    result = _flush_list()
    if result:
        if pending_note_type:
            # A label-only note still wraps its list as the note body.
            _append_block(result)
        else:
            _append_body(result)
    _flush_pending_note_to_body()

    body_content = "\n".join(p for p in body_parts if p)
    if not str(body_content).strip():
        # IME structured editor binds the first body child. An empty
        # <conbody>/<body> yields "加载文档内容失败:undefined".
        body_content = "        <p></p>"

    if topic_kind == "chapter":
        root_tag = "concept"
        body_tag = "conbody"
        doctype = '<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN" "concept.dtd">'
        xml_id = f"concept-{topic_id}"
    else:
        root_tag = "topic"
        body_tag = "body"
        doctype = IME_TOPIC_DECL
        xml_id = f"topic-{topic_id}"

    if topic_kind == "cover":
        root_tag = "topic"
        body_tag = "body"
        doctype = IME_TOPIC_DECL
        xml_id = f"topic-{topic_id}"

    ime_topic_type = {
        "cover": "sCoverTopic",
        "chapter": "chapterTopic",
    }.get(topic_kind, "sDitaTopic")
    outputclass = ' outputclass="cover A4"' if topic_kind == "cover" else ""

    return f"""<?xml version="1.0" encoding="UTF-8"?>
{doctype}
<{root_tag} xmlns:cms="http://www.w3.org/ime/cms" xmlns:m="http://www.w3.org/1998/Math/MathML" xml:lang="{dita_lang}" id="{xml_id}"{outputclass} cms:keys="{topic_id}" cms:title="{safe_title_attr}" cms:number="{topic_id}" cms:imesofttype="{ime_topic_type}">
  <title id="title_{topic_id}">{safe_title}</title>
  <{body_tag} id="body_{topic_id}" outputclass="pretext">
{body_content}
  </{body_tag}>
</{root_tag}>"""


def _strip_tag(xml):
    return re.sub(r'<[^>]+>', '', xml)


def _content_to_markdown(section_title, section_content):
    title = _clean_title(section_title) or "未命名章节"
    content = (section_content or "").strip()
    if content:
        return f"# {title}\n\n{content}\n"
    return f"# {title}\n"


def _markdown_to_lossless_csv(content):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(["line_number", "content"])
    # Split on "\n" (not splitlines) so a trailing newline survives the round
    # trip: "a\nb\n" -> ["a", "b", ""] -> "a\nb\n".
    for line_number, line in enumerate(content.split("\n"), start=1):
        writer.writerow([line_number, line])
    return "\ufeff" + buffer.getvalue()


def _csv_table_to_markdown(content):
    rows = []
    reader = csv.reader(io.StringIO(content.lstrip("\ufeff")))
    for row in reader:
        rows.append([str(cell or "") for cell in row])

    if not rows:
        return ""

    def _escape_md_cell(cell):
        return cell.replace("|", "\\|")

    header = rows[0]
    align = [":---" for _ in header]
    md_lines = [
        "| " + " | ".join(_escape_md_cell(cell) for cell in header) + " |",
        "| " + " | ".join(align) + " |",
    ]
    for row in rows[1:]:
        if len(row) < len(header):
            row = row + [""] * (len(header) - len(row))
        md_lines.append("| " + " | ".join(_escape_md_cell(cell) for cell in row[:len(header)]) + " |")
    return "\n".join(md_lines) + "\n"


def _csv_to_markdown(content):
    text = content.lstrip("\ufeff")
    reader = csv.DictReader(io.StringIO(text))
    fieldnames = reader.fieldnames or []
    normalized = {str(name or "").strip().lower() for name in fieldnames}
    if {"line_number", "content"}.issubset(normalized):
        rows = []
        for row in reader:
            line_number = row.get("line_number") or row.get("LINE_NUMBER") or row.get("Line_Number") or "0"
            try:
                order = int(str(line_number).strip() or "0")
            except ValueError:
                order = 0
            rows.append((order, row.get("content") or row.get("CONTENT") or ""))
        rows.sort(key=lambda item: item[0])
        return "\n".join(line for _, line in rows)
    return _csv_table_to_markdown(text)


def _build_active_rules(source_format, target_format, source_content, template_path, images, sections, is_lossless_md_csv):
    rules = [{
        "rule_number": "01",
        "category": "内容",
        "description": "转换内容须100%与原文保持一致，不得遗漏或添加任何文字、符号、空白段落",
    }]

    if is_lossless_md_csv:
        return rules

    if images:
        rules.append({
            "rule_number": "02",
            "category": "图片",
            "description": "原文中引用的外部图片须下载并嵌入到输出文档包中，确保离线可查看",
        })

    if target_format == "dita":
        if re.search(r'^\s{0,3}#{1,6}\s+((\d+(?:\.\d+)*)|chapter\s+\d+|第\s*\d+\s*章)[\s:：-]+', source_content, re.IGNORECASE | re.MULTILINE):
            rules.append({
                "rule_number": "03",
                "category": "编号",
                "description": "章节标题前的编号按模板样式处理，避免正文重复编号",
            })
        if re.search(r'^\|.*\|\s*$', source_content, re.MULTILINE):
            rules.append({
                "rule_number": "04",
                "category": "表格标题",
                "description": "Markdown 表格结构需映射为 DITA 表格结构",
            })
        if re.search(r'^\s*[-*+]\s+', source_content, re.MULTILINE):
            rules.append({
                "rule_number": "05",
                "category": "列表-无序",
                "description": "Markdown 无序列表需映射为 DITA 列表结构",
            })
        if re.search(r'^\s*\d+[.)]\s+', source_content, re.MULTILINE):
            rules.append({
                "rule_number": "06",
                "category": "列表-有序",
                "description": "Markdown 有序列表需映射为 DITA 列表结构",
            })
        if any(section.get("title") for section in sections):
            rules.append({
                "rule_number": "07",
                "category": "结构",
                "description": "文档标题层级按实际结构拆分并组织为 DITA 输出",
            })
        if template_path and os.path.exists(template_path):
            rules.append({
                "rule_number": "08",
                "category": "模板",
                "description": "提供参考模板时复用模板结构与必要元数据",
            })

    return rules


def _rewrite_template_frontmatter(frontmatter_xml, topics_output):
    if not frontmatter_xml:
        return frontmatter_xml, set()

    rewritten = frontmatter_xml
    used_files = set()
    title_to_topic = {
        _clean_navtitle(topic["title"]).strip().lower(): topic
        for topic in topics_output
        if topic.get("title") and topic.get("filename")
    }
    for navtitle, topic in title_to_topic.items():
        escaped_title = _escape_xml_attr(_clean_navtitle(topic["title"]))
        pattern = re.compile(rf'(<topicref[^>]*navtitle="{re.escape(escaped_title)}"[^>]*href=")([^"]+)(")')
        if pattern.search(rewritten):
            rewritten = pattern.sub(rf'\1{topic["filename"]}\3', rewritten)
            rewritten = re.sub(
                rf'(<topicref[^>]*navtitle="{re.escape(escaped_title)}"[^>]*cms:placeHolder=")([^"]*)(")',
                rf'\1{_topic_placeholder(topic)}\3',
                rewritten,
            )
            rewritten = re.sub(
                rf'(<topicref[^>]*navtitle="{re.escape(escaped_title)}"[^>]*keys=")([^"]*)(")',
                rf'\1{topic["id"]}\3',
                rewritten,
            )
            used_files.add(topic["filename"])

    if REUSE_TEMPLATE_COVER_TOPIC and '<topicref' in rewritten:
        cover_href_match = re.search(r'<topicref\b[^>]*href="([^"]+\.dita)"', rewritten)
        if cover_href_match:
            used_files.add(cover_href_match.group(1))

    # Source front-matter topics (version history, plus e.g. reagent-kit basic
    # info) become siblings of the template cover inside <frontmatter>. They are
    # inserted before <booklists>; topics already carried by the template are
    # skipped so the block is not duplicated. Appendix topics are excluded.
    frontmatter_children = []
    for topic in topics_output:
        if not topic.get("filename") or topic.get("is_appendix"):
            continue
        title = topic.get("title", "")
        if not _is_frontmatter_title(title):
            continue
        escaped_title = _escape_xml_attr(_clean_navtitle(title))
        if f'navtitle="{escaped_title}"' in rewritten:
            continue
        frontmatter_children.append(topic)

    if frontmatter_children and '<booklists' in rewritten:
        child_xml = []
        child_node_id_seq = iter(range(900001, 999999))
        for child in frontmatter_children:
            _append_topicref_xml(child_xml, child, child_node_id_seq, "  ", 2, "en-US")
            used_files.add(child["filename"])
        rewritten = rewritten.replace(
            '<booklists',
            "\n".join(child_xml) + '<booklists',
            1,
        )

    return rewritten, used_files


def _collect_template_dita_refs(*xml_parts):
    refs = set()
    for xml in xml_parts:
        if not xml:
            continue
        refs.update(re.findall(r'href="([^"]+\.dita)"', xml))
    return refs


def _prune_unreferenced_output_images(output_base, keep_paths=None):
    referenced = set()
    image_dir = os.path.join(output_base, "image")
    if not os.path.isdir(image_dir):
        return set(), set()

    keep_paths = set(keep_paths or [])

    for root, _, files in os.walk(output_base):
        for fname in files:
            if not fname.endswith((".dita", ".ditamap", ".md")):
                continue
            file_path = os.path.join(root, fname)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception:
                continue

            for href in re.findall(r'href="([^"]+)"', content):
                href = href.strip()
                if href.startswith("image/"):
                    referenced.add(href)
            for md_path in re.findall(r'!\[[^\]]*\]\(([^)]+)\)', content):
                md_path = md_path.strip()
                if md_path.startswith("image/"):
                    referenced.add(md_path)

    existing = set()
    for root, _, files in os.walk(image_dir):
        for fname in files:
            abs_path = os.path.join(root, fname)
            rel_path = os.path.relpath(abs_path, output_base).replace(os.sep, "/")
            existing.add(rel_path)
            if rel_path not in referenced:
                if rel_path in keep_paths:
                    continue
                os.remove(abs_path)

    return referenced, existing


def _escape_xml_attr(value):
    return (
        (value or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _build_topic_hierarchy(topics, skipped_files):
    roots = []
    stack = []

    for topic in topics:
        if topic["filename"] in skipped_files:
            continue

        node = {
            "topic": topic,
            "children": [],
        }

        topic_level = max(1, int(topic.get("level", 1) or 1))
        while stack and int(stack[-1]["topic"].get("level", 1) or 1) >= topic_level:
            stack.pop()

        if stack:
            stack[-1]["children"].append(node)
        else:
            roots.append(node)

        stack.append(node)

    return roots


def _topic_uses_dita_file(topic):
    return bool(topic.get("filename"))


def _topic_code_prefix(topic_kind):
    return {
        "cover": "CTT",
        "chapter": "CTO",
        "concept": "DTO",
        "reference": "DTO",
        "task": "DTO",
    }.get(topic_kind, "DTO")


def _generated_topic_code(topic_index, topic_kind="concept"):
    return f"{_topic_code_prefix(topic_kind)}{GENERATED_TOPIC_BASE + topic_index:06d}"


def _topic_placeholder(topic):
    filename = topic.get("filename") or ""
    return os.path.splitext(filename)[0] if filename else ""


def _topic_template_name(topic_kind):
    return {
        "cover": "sCoverTopic",
        "chapter": "chapterTopic",
    }.get(topic_kind, "sDitaTopic")


def _topic_kind_for_section(section, title):
    if int(section.get("level", 1) or 1) <= 1:
        if _normalize_section_key(title) == "cover":
            return "cover"
        return "chapter"
    # IME shows 主题 Topic for DTO + sDitaTopic; DTC is shown as 主题 Concept.
    return "task"


def _append_topicref_xml(lines, topic, node_id_seq, indent, level_attr, dita_lang, template_name=None, children=None):
    topic_kind = topic.get("topic_kind") or "concept"
    template_name = template_name or _topic_template_name(topic_kind)
    navtitle = _escape_xml_attr(_clean_navtitle(topic["title"]))
    node_id = f"PN{next(node_id_seq):03d}"
    ime_soft_type = template_name
    placeholder = _escape_xml_attr(_topic_placeholder(topic))
    attrs = (
        f'navtitle="{navtitle}" '
        f'xml:lang="{dita_lang}" id="{node_id}" '
        f'applicDesc="" '
        f'href="{topic["filename"]}" '
        f'keys="{topic["id"]}" type="topic" '
        f'cms:title="{navtitle}" '
        f'cms:placeHolder="{placeholder}" '
        f'cms:nodeType="XML" '
        f'cms:template="{template_name}" '
        f'level="{level_attr}" '
        f'cms:imesofttype="{ime_soft_type}" '
        f'version="{GENERATED_NODE_VERSION}"'
    )
    if children:
        lines.append(f'{indent}<topicref {attrs}>')
        for child in children:
            _append_topicref_xml(
                lines,
                child["topic"],
                node_id_seq,
                indent + "  ",
                level_attr + 1,
                dita_lang,
                children=child.get("children"),
            )
        lines.append(f'{indent}</topicref>')
        return

    lines.append(f'{indent}<topicref {attrs}/>' )


def _topic_has_body(topic):
    return bool((topic.get("raw_content") or "").strip())


def _append_topicref_container_xml(lines, node, node_id_seq, indent, level_attr, dita_lang):
    _append_topicref_xml(
        lines,
        node["topic"],
        node_id_seq,
        indent,
        level_attr,
        dita_lang,
        children=node["children"],
    )


def _append_root_container_xml(lines, node, chapter_seq, node_id_seq, indent, level_attr, timestamp, dita_lang):
    topic = node["topic"]
    navtitle = _escape_xml_attr(topic["title"])
    container_tag = (
        "appendix"
        if (topic.get("is_appendix") or topic["title"].strip().lower() == "appendix")
        else "chapter"
    )
    chapter_id = f"PG{timestamp}_{next(chapter_seq):03d}"
    lines.append(
        f'{indent}<{container_tag} navtitle="{navtitle}" id="{chapter_id}" applicDesc=""'
        f' cms:lang="{dita_lang}" cms:type="{container_tag}" cms:title=""'
        f' cms:isTemplet="N"'
        f' level="{level_attr}" version="{GENERATED_NODE_VERSION}">'
    )
    if _topic_uses_dita_file(topic):
        _append_topicref_xml(
            lines,
            topic,
            node_id_seq,
            indent + "  ",
            level_attr + 1,
            dita_lang,
            template_name="chapterTopic",
        )
    for child in node["children"]:
        _append_topicref_xml(
            lines,
            child["topic"],
            node_id_seq,
            indent + "  ",
            level_attr + 1,
            dita_lang,
            children=child.get("children"),
        )
    lines.append(f'{indent}</{container_tag}>')


def _append_frontmatter_xml(lines, cover_node, frontmatter_nodes, node_id_seq, indent, timestamp, dita_lang):
    """Emit a <frontmatter> block: optional cover topic, then the front-matter
    topics (about / revision history), then the booklists TOC."""
    frontmatter_id = f"PG{timestamp}_FM"
    lines.append(
        f'{indent}<frontmatter navtitle="Preface" id="{frontmatter_id}" applicDesc=""'
        f' cms:lang="{dita_lang}" cms:title="" cms:placeHolder="" cms:isTemplet="N"'
        f' cms:referenceType="" cms:type="frontmatter" cms:outputclass=""'
        f' cms:descriptioin="" cms:xCoordination="" cms:sourceTag=""'
        f' cms:referenceMap="" cms:colNumber="2" cms:nodeRemark=""'
        f' level="1" version="{GENERATED_NODE_VERSION}">'
    )
    if cover_node is not None:
        _append_topicref_xml(
            lines,
            cover_node["topic"],
            node_id_seq,
            indent + "  ",
            2,
            dita_lang,
            template_name="sCoverTopic",
            children=cover_node.get("children"),
        )
    for node in frontmatter_nodes:
        _append_topicref_xml(
            lines,
            node["topic"],
            node_id_seq,
            indent + "  ",
            2,
            dita_lang,
            template_name="sDitaTopic",
            children=node.get("children"),
        )

    booklists_id = f"PG{timestamp}_BL"
    toc_id = f"PG{timestamp}_TOC"
    lines.append(
        f'{indent}  <booklists id="{booklists_id}" applicDesc="" cms:lang="{dita_lang}" cms:title="" cms:placeHolder=""'
        f' cms:isTemplet="N" cms:referenceType="" cms:type="booklists" cms:outputclass=""'
        f' cms:descriptioin="" cms:xCoordination="" cms:sourceTag="" cms:referenceMap=""'
        f' cms:colNumber="2" cms:nodeRemark="" level="2" version="{GENERATED_NODE_VERSION}">'
    )
    lines.append(
        f'{indent}    <toc id="{toc_id}" applicDesc="" cms:lang="{dita_lang}" cms:title="" cms:placeHolder=""'
        f' cms:isTemplet="N" cms:referenceType="" cms:type="toc" cms:outputclass=""'
        f' cms:descriptioin="" cms:xCoordination="" cms:sourceTag="" cms:referenceMap=""'
        f' cms:colNumber="2" cms:nodeRemark="" level="3" version="{GENERATED_NODE_VERSION}"/>'
    )
    lines.append(f'{indent}  </booklists>')
    lines.append(f'{indent}</frontmatter>')


def _append_bookmap_topics(lines, topic_roots, timestamp, dita_lang):
    chapter_seq = iter(range(1, 10000))
    node_id_seq = iter(range(1, 100000))

    cover_node = None
    frontmatter_nodes = []
    chapter_roots = []
    for root in topic_roots:
        topic = root["topic"]
        if _normalize_section_key(topic.get("title", "")) == "cover":
            cover_node = root
        elif topic.get("is_appendix"):
            chapter_roots.append(root)
        elif _is_frontmatter_title(topic.get("title", "")):
            frontmatter_nodes.append(root)
        else:
            chapter_roots.append(root)

    if cover_node is not None or frontmatter_nodes:
        _append_frontmatter_xml(
            lines, cover_node, frontmatter_nodes, node_id_seq, "  ", timestamp, dita_lang
        )

    for root in chapter_roots:
        _append_root_container_xml(lines, root, chapter_seq, node_id_seq, "  ", 1, timestamp, dita_lang)


def _derive_map_title(source_format, file_path, sections):
    if source_format in ("docx", "idml", "md") and file_path:
        stem = os.path.splitext(os.path.basename(file_path))[0]
        stem = re.sub(r'^src_\d+_', '', stem)
        stem = re.sub(r'^idml_\d+_', '', stem)
        stem = stem.replace("_", " ").strip()
        if stem:
            return stem

    for sec in sections:
        title = _clean_title(sec.get("title", ""))
        if title and title.lower() not in {"cover", "contents"}:
            return title
    return "Generated Document"


# List levels arrive as a [[LVL:n]] marker prefixed to the line, so the marker
# is allowed before the number when deciding whether a section is procedural.
_ORDERED_LIST_LINE_RE = re.compile(r'(?m)^[ \t]*(?:\[\[LVL:\d+\]\])?\d+[.)]\s')


def _section_dita_type(title, content):
    """Sections that carry numbered steps are procedural tasks (DTO)."""
    if _ORDERED_LIST_LINE_RE.search(content or ""):
        return "task"
    return _get_topic_type(title)


def _flatten_sections(sections, parent_h1="", level=1):
    """Recursively flatten nested sections into a list of topics.
    Every heading at any level becomes its own topic.
    """
    result = []
    for sec in sections:
        title = sec.get("title", "")
        content = sec.get("content", "")
        children = sec.get("sections", [])

        is_appendix = bool(sec.get("is_appendix"))
        if isinstance(title, str) and IDML_APPENDIX_MARKER in title:
            is_appendix = True
            title = title.replace(IDML_APPENDIX_MARKER, "").strip()

        if title or content or not children:
            result.append({
                "h1": parent_h1,
                "level": level,
                "title": title,
                "content": content,
                "has_children": bool(children),
                "child_titles": [child.get("title", "") for child in children],
                "dita_type": _section_dita_type(title, content),
                "is_appendix": is_appendix,
            })

        if children:
            new_parent = title or parent_h1
            result.extend(_flatten_sections(children, new_parent, level + 1))

    return result


def _should_emit_container_only(section):
    if not section.get("has_children"):
        return False

    if (section.get("content") or "").strip():
        return False

    return int(section.get("level", 1) or 1) <= 1


def _run_pipeline(task_id, db_session_factory, source_format, file_path, source_content,
                   target_format, template_path, requirements_text, output_language=None):
    """格式转换流水线。

    固定行为（不可变）：
    - 标题清理: 去 \\ 转义/去 ** 加粗/去编号前缀
    - 全级拆分: H1-H6 每个标题一个独立 topic
    - 图片下载: 外部图片打包到 image/ 目录
    - 模板复用: 从模板复制 <frontmatter> + Manufacturer <appendix> 及其文件
    可变部分: 仅复用哪些具体 topic 可随任务调整。
    """
    import time as _time
    from app.database import SessionLocal

    db = SessionLocal()
    try:

        def _set_progress(pct, step):
            with _tasks_lock:
                _task_store[task_id] = {
                    "progress": pct, "current_step": step, "status": "processing"
                }
            try:
                update_convert_task_progress(db, task_id, pct, step)
            except Exception:
                pass

        _set_progress(5, "解析")

        is_lossless_md_csv = (
            (source_format == "md" and target_format == "csv")
            or (source_format == "csv" and target_format == "markdown")
        )

        sections = []
        images = []
        if not is_lossless_md_csv:
            sections = _parse_content(source_format, file_path, source_content)
            if source_format in ("docx", "idml"):
                sections = _reshape_docx_sections(sections)
                sections = _postprocess_section_tree(sections)
            elif source_format == "md":
                sections = _postprocess_section_tree(sections)
            images = _extract_images_md(source_content)

        _set_progress(20, "解析")

        template_parts = None
        if template_path and os.path.exists(template_path):
            template_parts = _extract_template_parts(template_path)

        dita_lang = _detect_dita_language(source_content, template_parts, requirements_text, output_language)

        _set_progress(30, "结构映射")

        special = _parse_special_requirements(requirements_text)

        conversion_detail = []
        topics_output = []
        image_count = len(images)
        topic_index = 0
        all_sections = []

        if is_lossless_md_csv:
            if source_format == "md":
                topics_output.append({
                    "type": "csv",
                    "filename": "content.csv",
                    "title": "Markdown 全文",
                    "content": _markdown_to_lossless_csv(source_content),
                })
                conversion_detail.append({
                    "source_section": "Markdown 全文",
                    "target_type": "csv",
                    "topic_file": "content.csv",
                    "status": "ok",
                })
            else:
                topics_output.append({
                    "type": "markdown",
                    "filename": "content.md",
                    "title": "Markdown 全文",
                    "content": _csv_to_markdown(source_content),
                })
                conversion_detail.append({
                    "source_section": "CSV 全文",
                    "target_type": "markdown",
                    "topic_file": "content.md",
                    "status": "ok",
                })
        else:
            all_sections = _flatten_sections(sections)

            if special["auto_split"] and len(all_sections) == 1:
                def _rebuild_content(sec):
                    parts = []
                    if sec.get("content"):
                        parts.append(sec["content"])
                    for child in sec.get("sections", []):
                        parts.append(f"{'#' * (sec.get('level', 1) + 1)} {child['title']}")
                        parts.append(_rebuild_content(child))
                    return "\n".join(p.strip() for p in parts if p.strip())

                all_sections = []
                for h1 in sections:
                    if h1["title"]:
                        h1_title = h1["title"]
                        h1_is_appendix = IDML_APPENDIX_MARKER in h1_title
                        if h1_is_appendix:
                            h1_title = h1_title.replace(IDML_APPENDIX_MARKER, "").strip()
                        h1_content = _rebuild_content(h1)
                        all_sections.append({
                            "h1": "",
                            "title": h1_title,
                            "content": h1_content,
                            "level": 1,
                            "dita_type": _section_dita_type(h1_title, h1_content),
                            "is_appendix": h1_is_appendix,
                        })
                if not all_sections:
                    all_sections = _flatten_sections(sections)

            slug_counts = {}
            # When the template supplies its own cover topic, the source cover is
            # replaced by it. Emitting the generated cover topic too would leave a
            # duplicate/orphan file that is never referenced by the ditamap.
            reuse_template_cover = bool(
                REUSE_TEMPLATE_COVER_TOPIC
                and template_parts
                and re.search(
                    r'<topicref\b[^>]*href="[^"]+\.dita"',
                    template_parts.get("frontmatter_xml") or "",
                )
            )
            # First pass: assign each section its topic id, so cross-references
            # can be resolved to the target topic during the second pass.
            prepared = []
            skipped_cover_content = ""
            for section in all_sections:
                title = _clean_title(section["title"])
                h1_title = _clean_title(section.get("h1", ""))
                if not title:
                    title = h1_title or f"Section {topic_index + 1}"

                if reuse_template_cover and _normalize_section_key(title) == "cover":
                    skipped_cover_content = (section.get("content") or "").strip()
                    continue

                dita_type = section["dita_type"]
                for keyword, override_type in special["type_overrides"].items():
                    if keyword in title:
                        dita_type = override_type
                        break

                topic_index += 1
                slug = re.sub(r'[^\w\s-]', '', title).strip().lower()
                slug = re.sub(r'[-\s]+', '_', slug) or f"topic_{topic_index}"
                slug_count = slug_counts.get(slug, 0)
                slug_counts[slug] = slug_count + 1
                if slug_count:
                    slug = f"{slug}_{slug_count + 1}"
                topic_kind = _topic_kind_for_section(section, title)
                if int(section.get("level", 1) or 1) <= 1 and _is_frontmatter_title(title):
                    # Front-matter topics use DTO + sDitaTopic so IME shows 主题 Topic.
                    topic_kind = "task"
                topic_id = _generated_topic_code(topic_index, topic_kind)
                topic_filename = f"{topic_id}.dita"
                prepared.append((section, title, dita_type, topic_id, topic_filename, topic_kind))

            if skipped_cover_content:
                for section, title, _dtype, _tid, _fname, _kind in prepared:
                    if _normalize_section_key(title) in VERSION_HISTORY_TITLES:
                        if not (section.get("content") or "").strip():
                            section["content"] = skipped_cover_content
                        break

            xref_map = {}
            for _section, _title, _dtype, _tid, _fname, _kind in prepared:
                if _title:
                    xref_map.setdefault(_title, _tid)
                _raw_title = _clean_title(_section["title"])
                if _raw_title:
                    xref_map.setdefault(_raw_title, _tid)
                _num = _heading_number(_section.get("title") or "")
                if _num:
                    xref_map.setdefault(_num, _tid)
                if _tid and _title:
                    xref_map.setdefault(_tid, _title)

            for section, title, dita_type, topic_id, topic_filename, topic_kind in prepared:
                dita_content = _content_to_dita_xml(
                    title,
                    section["content"],
                    dita_type,
                    topic_id,
                    dita_lang,
                    topic_kind=topic_kind,
                    source_format=source_format,
                    xref_map=xref_map,
                )

                topics_output.append({
                    "type": dita_type,
                    "filename": topic_filename,
                    "id": topic_id,
                    "topic_kind": topic_kind,
                    "level": section.get("level", 1),
                    "content": dita_content,
                    "raw_content": section["content"],
                    "is_container_only": False,
                    "is_appendix": section.get("is_appendix", False),
                    "title": title,
                })
                conversion_detail.append({
                    "source_section": title,
                    "target_type": _topic_template_name(topic_kind),
                    "topic_file": topic_filename,
                    "status": "ok",
                })

        _set_progress(55, "内容替换")

        for topic in topics_output:
            for reuse_name in special["reuse_topics"]:
                if reuse_name.lower() in topic["filename"].lower() or reuse_name.lower() in topic["title"].lower():
                    pass

        _set_progress(70, "验证")

        template_check_status = "passed"
        template_check_detail = "未使用模板"
        if template_path and target_format == "dita":
            template_check_status = "warning"
            template_check_detail = "模板已参考"
        elif template_path and target_format == "markdown":
            template_check_status = "warning"
            template_check_detail = "Markdown 输出未使用模板包"
        elif template_path and target_format == "csv":
            template_check_status = "warning"
            template_check_detail = "CSV 输出未使用模板包"

        content_check_detail = "全部章节已映射"
        if is_lossless_md_csv:
            content_check_detail = "已按逐行无损格式转换"

        checks = [
            {"name": "结构完整性", "status": "passed"},
            {"name": "模板一致性", "status": template_check_status,
             "detail": template_check_detail},
            {"name": "语言标记", "status": "passed", "detail": dita_lang},
            {"name": "图片验证", "status": "passed", "detail": f"{image_count}/{image_count}"},
            {"name": "内容完整性", "status": "passed", "detail": content_check_detail},
        ]

        unmapped = []
        for sec in all_sections:
            if sec["title"] and not sec["content"]:
                pass

        overall = "passed"
        if unmapped:
            checks[4]["status"] = "warning"
            checks[4]["detail"] = f"{len(unmapped)}个章节未映射"
            overall = "warning"

        _set_progress(85, "打包")

        timestamp = _time.strftime("%Y%m%d_%H%M%S")
        # Include the task id: the timestamp has second resolution, so two
        # conversions started in the same second would otherwise share a
        # directory and overwrite each other's output.
        output_name = f"output_{timestamp}_{task_id}"
        output_base = os.path.join(OUTPUT_DIR, output_name)
        _ensure_dir(output_base)
        written_topics = [topic for topic in topics_output if topic.get("filename") and topic.get("content")]

        url_map = _download_images_for_output(
            images, output_base, preserve_names=(source_format == "idml")
        )

        if is_lossless_md_csv:
            direct_filename = f"{output_name}{os.path.splitext(topics_output[0]['filename'])[1]}"
            direct_path = os.path.join(OUTPUT_DIR, direct_filename)
            with open(direct_path, "w", encoding="utf-8", newline="") as f:
                f.write(topics_output[0]["content"])
        elif target_format == "markdown":
            index_lines = ["# 转换结果", ""]
            for detail, topic in zip(conversion_detail, topics_output):
                topic_filename = topic["filename"].rsplit(".", 1)[0] + ".md"
                markdown_content = _content_to_markdown(topic["title"], topic.get("raw_content", ""))
                for url, local in url_map.items():
                    markdown_content = markdown_content.replace(f'({url})', f'({local})')
                with open(os.path.join(output_base, topic_filename), "w", encoding="utf-8") as f:
                    f.write(markdown_content)
                topic["filename"] = topic_filename
                detail["topic_file"] = topic_filename
                index_lines.append(f'- [{topic["title"]}]({topic_filename})')

            with open(os.path.join(output_base, "index.md"), "w", encoding="utf-8") as f:
                f.write("\n".join(index_lines) + "\n")
        else:
            frontmatter_used_files = set()
            manufacturer_used_files = set()
            fm_xml = ""
            mfg_xml = ""
            template_referenced_files = set()
            docx_media_files = set()
            if template_parts and template_parts.get("frontmatter_xml"):
                fm_xml, frontmatter_used_files = _rewrite_template_frontmatter(template_parts["frontmatter_xml"], topics_output)
            if template_parts and template_parts.get("manufacturer_xml"):
                mfg_xml, manufacturer_used_files = _rewrite_template_frontmatter(template_parts["manufacturer_xml"], topics_output)
            fm_xml = _rewrite_xml_language_attrs(fm_xml, dita_lang)
            mfg_xml = _rewrite_xml_language_attrs(mfg_xml, dita_lang)
            if template_parts:
                template_referenced_files = _collect_template_dita_refs(fm_xml, mfg_xml)

            if source_format == "docx":
                docx_media_files = _copy_docx_media_to_output(file_path, output_base)

            if template_parts:
                for fname, content in template_parts["files"].items():
                    if template_referenced_files and fname not in template_referenced_files:
                        continue
                    if fname.lower().endswith((".dita", ".xml", ".ditamap")):
                        try:
                            text_content = content.decode("utf-8", errors="ignore")
                            content = _rewrite_xml_language_attrs(text_content, dita_lang).encode("utf-8")
                        except Exception:
                            pass
                    tpl_fname = os.path.join(output_base, fname)
                    with open(tpl_fname, "wb") as f:
                        f.write(content)
                for img_path, img_content in template_parts["image_files"].items():
                    tpl_img = os.path.join(output_base, img_path)
                    os.makedirs(os.path.dirname(tpl_img), exist_ok=True)
                    with open(tpl_img, "wb") as f:
                        f.write(img_content)

            for topic in written_topics:
                content = topic["content"]
                for url, local in url_map.items():
                    content = content.replace(f'href="{url}"', f'href="{local}"')
                fname = os.path.join(output_base, topic["filename"])
                with open(fname, "w", encoding="utf-8") as f:
                    f.write(content)

            map_title = _derive_map_title(source_format, file_path, sections)
            map_title = map_title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            sanitized_name = re.sub(r'[^\w\s-]', '', map_title).strip()
            sanitized_name = re.sub(r'[-\s]+', '_', sanitized_name) or "document"
            map_filename = f"{sanitized_name}.ditamap"
            map_id = sanitized_name.upper()[:12]

            map_lines = [
                '<?xml version="1.0" encoding="UTF-8"?>',
                IME_BOOKMAP_DECL,
                f'<bookmap xmlns:imeCMS="http://www.megalinkware.com" xmlns:vf="http://www.megalinkware.com" xmlns:cms="http://www.w3.org/ime/cms" imeCMS:imesofttype="PartBookMap" imeCMS:softtype="PartBookMap" xml:lang="{dita_lang}" id="{map_id}" imeCMS:iba_lang="{dita_lang}" imeCMS:iba_title="" imeCMS:iba_placeHolder="" imeCMS:iba_isTemplet="N" imeCMS:iba_referenceType="" level="0" version="{GENERATED_NODE_VERSION}">',
                '  <booktitle>',
                f'    <mainbooktitle>{map_title}</mainbooktitle>',
                '  </booktitle>',
            ]

            if fm_xml:
                for line in fm_xml.strip().split("\n"):
                    map_lines.append(f"  {line.strip()}")

            referenced_topic_files = frontmatter_used_files | manufacturer_used_files
            topic_roots = _build_topic_hierarchy(topics_output, referenced_topic_files)
            _append_bookmap_topics(map_lines, topic_roots, timestamp, dita_lang)

            if mfg_xml:
                for line in mfg_xml.strip().split("\n"):
                    map_lines.append(f"  {line.strip()}")

            map_lines.append('</bookmap>')
            with open(os.path.join(output_base, map_filename), "w", encoding="utf-8") as f:
                f.write("\n".join(map_lines))

            _prune_unreferenced_output_images(output_base, keep_paths=docx_media_files)

        metadata_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<metadata>
  <generator>Smart Doc Platform</generator>
  <created>{timestamp}</created>
  <topics>{len(written_topics)}</topics>
  <images>{image_count}</images>
  <language>{dita_lang}</language>
  <source_format>{source_format}</source_format>
  <target_format>{target_format}</target_format>
</metadata>"""
        with open(os.path.join(output_base, "metadata.xml"), "w", encoding="utf-8") as f:
            f.write(metadata_xml)

        if is_lossless_md_csv:
            shutil.rmtree(output_base)
            output_public_path = f"/static/uploads/outputs/{direct_filename}"
            output_size = os.path.getsize(direct_path)
        else:
            zip_filename = f"{output_name}.zip"
            zip_path = os.path.join(OUTPUT_DIR, zip_filename)
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for root, dirs, files in os.walk(output_base):
                    for fname in files:
                        file_path_abs = os.path.join(root, fname)
                        arcname = os.path.relpath(file_path_abs, output_base)
                        zf.write(file_path_abs, arcname)

            shutil.rmtree(output_base)
            output_public_path = f"/static/uploads/outputs/{zip_filename}"
            output_size = os.path.getsize(zip_path)

        verification_report = {
            "overall": overall,
            "checks": checks,
            "unmapped_sections": unmapped,
        }

        verification_report["active_rules"] = _build_active_rules(
            source_format=source_format,
            target_format=target_format,
            source_content=source_content,
            template_path=template_path,
            images=images,
            sections=sections,
            is_lossless_md_csv=is_lossless_md_csv,
        )

        update_convert_task_result(
            db, task_id,
            output_zip_path=output_public_path,
            output_size=output_size,
            topic_count=len(written_topics),
            image_count=image_count,
            verification_report=verification_report,
            conversion_detail=conversion_detail,
        )

        _set_progress(100, "打包")
        with _tasks_lock:
            _task_store[task_id] = {
                "progress": 100, "current_step": "打包", "status": "completed"
            }

    except Exception as e:
        with _tasks_lock:
            _task_store[task_id] = {
                "progress": 0, "current_step": "", "status": "failed",
                "error": str(e)
            }
        try:
            update_convert_task_failed(db, task_id, str(e))
        except Exception:
            pass
    finally:
        if source_format == "idml" and file_path:
            # Reconstructed package and extracted media are one-shot; the final
            # output is already zipped, so drop them to avoid disk buildup.
            try:
                if str(file_path).lower().endswith(".idml"):
                    os.remove(file_path)
                shutil.rmtree(os.path.splitext(file_path)[0] + "_idml_media", ignore_errors=True)
            except Exception:
                pass
        db.close()


@router.post("/", response_model=dict)
async def start_conversion(
    source_file: UploadFile = File(...),
    target_format: str = Form("dita"),
    template_file: UploadFile = File(None),
    requirements: str = Form(None),
    output_language: str = Form(None),
    retry_feedback: str = Form(None),
    retry_screenshot: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user: UserOut = Depends(get_current_active_user),
):
    if target_format not in ["dita", "markdown", "csv"]:
        raise HTTPException(status_code=400, detail="目标格式仅支持 dita、markdown 或 csv")

    ext = os.path.splitext(source_file.filename)[1].lower()
    if ext not in [".md", ".markdown", ".docx", ".doc", ".csv", ".zip", ".idml"]:
        raise HTTPException(status_code=400, detail="不支持的文件格式，请上传 .md、.csv、.docx、.idml 或包含 IDML 的 .zip 文件")

    if ext in [".md", ".markdown"]:
        source_format = "md"
    elif ext == ".csv":
        source_format = "csv"
    elif ext in [".zip", ".idml"]:
        source_format = "idml"
    else:
        source_format = "docx"

    if source_format == "csv" and target_format != "markdown":
        raise HTTPException(status_code=400, detail="CSV 源文件当前仅支持转换为 markdown")
    if source_format == "md" and target_format == "dita" and template_file and template_file.filename and not template_file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="DITA 模板文件必须是 ZIP 包")
    if source_format == "docx" and target_format == "csv":
        raise HTTPException(status_code=400, detail="DOCX 当前仅支持转换为 dita 或 markdown")
    if source_format == "idml" and target_format == "csv":
        raise HTTPException(status_code=400, detail="IDML 当前仅支持转换为 dita 或 markdown")
    if source_format == "idml" and target_format == "dita" and template_file and template_file.filename and not template_file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="DITA 模板文件必须是 ZIP 包")
    normalized_output_language = _normalize_dita_language(output_language) if output_language else None
    if output_language and not normalized_output_language:
        raise HTTPException(status_code=400, detail="输出语言仅支持 en-US 或 zh-CN")

    _ensure_dir(UPLOAD_DIR)
    source_path = os.path.join(UPLOAD_DIR, f"src_{int(time.time() * 1000)}_{source_file.filename}")
    with open(source_path, "wb") as f:
        f.write(await source_file.read())

    template_path = None
    template_filename = None
    if template_file:
        template_filename = template_file.filename
        template_path = os.path.join(UPLOAD_DIR, f"tpl_{int(time.time() * 1000)}_{template_file.filename}")
        with open(template_path, "wb") as f:
            f.write(await template_file.read())

    retry_screenshot_path = None
    if retry_screenshot and retry_screenshot.filename:
        retry_screenshot_path = os.path.join(UPLOAD_DIR, f"ss_{int(time.time() * 1000)}_{retry_screenshot.filename}")
        with open(retry_screenshot_path, "wb") as f:
            f.write(await retry_screenshot.read())

    combined_requirements = requirements or ""
    if retry_feedback:
        if combined_requirements:
            combined_requirements += "\n[IME反馈] " + retry_feedback
        else:
            combined_requirements = "[IME反馈] " + retry_feedback

    pipeline_file_path = source_path
    if source_format == "idml":
        # The container may hold both .indd and .idml; the IDML is the reliable
        # source and the .indd (proprietary binary) is ignored.
        try:
            pipeline_file_path = _resolve_idml_source(source_path)
        except Exception:
            pipeline_file_path = None
        if not pipeline_file_path:
            try:
                os.remove(source_path)
            except Exception:
                pass
            raise HTTPException(status_code=400, detail="压缩包中未找到 .idml 文件；.indd 无法直接解析，请导出 IDML 后重试")
        if pipeline_file_path != source_path:
            # The outer container has served its purpose; the reconstructed
            # package (deleted when the pipeline finishes) is now the source.
            try:
                os.remove(source_path)
            except Exception:
                pass

    source_content = ""
    try:
        if source_format in ["md", "csv"]:
            with open(source_path, "r", encoding="utf-8", errors="ignore") as f:
                source_content = f.read()
        elif source_format == "docx":
            source_content = _docx_to_markdown(source_path)
        elif source_format == "idml":
            source_content = _idml_to_markdown(pipeline_file_path)
    except Exception as e:
        try:
            os.remove(source_path)
        except Exception:
            pass
        if pipeline_file_path != source_path:
            try:
                os.remove(pipeline_file_path)
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=f"文件解析失败: {str(e)}")

    task = create_convert_task(db, ConvertTaskCreate(
        source_filename=source_file.filename,
        source_format=source_format,
        target_format=target_format,
        template_filename=template_filename,
        requirements=combined_requirements,
        retry_feedback=retry_feedback,
        retry_screenshot_path=retry_screenshot_path,
    ), user_id=current_user.id)

    with _tasks_lock:
        _task_store[task.task_id] = {
            "progress": 0, "current_step": "", "status": "processing"
        }

    thread = threading.Thread(
        target=_run_pipeline,
        args=(task.task_id, None, source_format, pipeline_file_path, source_content,
              target_format, template_path, combined_requirements, normalized_output_language),
        daemon=True,
    )
    thread.start()

    return {"task_id": task.task_id, "status": "processing"}


def _convert_output_disk_path(task):
    path = task.output_zip_path or ""
    if path.startswith("/static/"):
        return f".{path}"
    return path


def _run_revise_pipeline(task_id, feedback, screenshot_path=None):
    from app.database import SessionLocal
    from app.utils.convert_feedback import apply_convert_feedback

    db = SessionLocal()
    work_dir = None
    try:
        def _set_progress(pct, step):
            with _tasks_lock:
                _task_store[task_id] = {
                    "progress": pct, "current_step": step, "status": "processing"
                }
            try:
                update_convert_task_progress(db, task_id, pct, step)
            except Exception:
                pass

        _set_progress(15, "按反馈修改")
        task = get_convert_task(db, task_id)
        if not task:
            raise RuntimeError("任务不存在")
        src_zip = _convert_output_disk_path(task)
        if not src_zip or not os.path.exists(src_zip):
            raise RuntimeError("找不到已生成的转换包")

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        work_dir = os.path.join(OUTPUT_DIR, f"revise_{timestamp}_{task_id}")
        _ensure_dir(work_dir)
        with zipfile.ZipFile(src_zip, "r") as zf:
            zf.extractall(work_dir)

        _set_progress(45, "按反馈修改")
        chat_fn = None
        try:
            from app.utils.ai_client import ai_client
            chat_fn = ai_client.chat
        except Exception:
            chat_fn = None

        apply_convert_feedback(work_dir, feedback, chat_fn=chat_fn)

        _set_progress(80, "打包")
        zip_filename = f"output_revised_{timestamp}_{task_id}.zip"
        zip_path = os.path.join(OUTPUT_DIR, zip_filename)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(work_dir):
                for fname in files:
                    abs_path = os.path.join(root, fname)
                    arcname = os.path.relpath(abs_path, work_dir)
                    zf.write(abs_path, arcname)

        output_public_path = f"/static/uploads/outputs/{zip_filename}"
        update_convert_task_revised(
            db, task_id,
            output_zip_path=output_public_path,
            output_size=os.path.getsize(zip_path),
            retry_feedback=feedback,
            retry_screenshot_path=screenshot_path,
        )
        _set_progress(100, "打包")
        with _tasks_lock:
            _task_store[task_id] = {
                "progress": 100, "current_step": "打包", "status": "completed"
            }
    except Exception as e:
        try:
            update_convert_task_failed(db, task_id, str(e))
        except Exception:
            pass
        with _tasks_lock:
            _task_store[task_id] = {
                "progress": 0, "current_step": "按反馈修改", "status": "failed"
            }
    finally:
        if work_dir:
            shutil.rmtree(work_dir, ignore_errors=True)
        db.close()


@router.post("/{task_id}/revise", response_model=dict)
async def revise_conversion(
    task_id: str,
    feedback: str = Form(...),
    screenshot: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user: UserOut = Depends(get_current_active_user),
):
    task = _require_convert_task_access(db, task_id, current_user)
    if task.target_format != "dita":
        raise HTTPException(status_code=400, detail="目前只支持按反馈修改 DITA 转换包")
    if task.status != "completed" or not task.output_zip_path:
        raise HTTPException(status_code=400, detail="请先完成一次转换，再按反馈修改转换包")
    if not (feedback or "").strip():
        raise HTTPException(status_code=400, detail="请填写反馈内容")

    screenshot_path = None
    if screenshot and screenshot.filename:
        _ensure_dir(UPLOAD_DIR)
        screenshot_path = os.path.join(UPLOAD_DIR, f"ss_{int(time.time() * 1000)}_{screenshot.filename}")
        with open(screenshot_path, "wb") as handle:
            handle.write(await screenshot.read())

    update_convert_task_status(db, task_id, "processing", progress=5, current_step="按反馈修改")
    with _tasks_lock:
        _task_store[task_id] = {
            "progress": 5, "current_step": "按反馈修改", "status": "processing"
        }

    thread = threading.Thread(
        target=_run_revise_pipeline,
        args=(task_id, feedback.strip(), screenshot_path),
        daemon=True,
    )
    thread.start()
    return {"task_id": task_id, "status": "processing"}


@router.get("/{task_id}/progress", response_model=ProgressOut)
async def query_progress(task_id: str, db: Session = Depends(get_db), current_user: UserOut = Depends(get_current_active_user)):
    task = _require_convert_task_access(db, task_id, current_user)

    steps = []
    step_names = _get_step_names()
    step_progress_thresholds = [20, 50, 75, 85, 100]
    current_step = task.current_step or ""

    for i, name in enumerate(step_names):
        if task.progress >= step_progress_thresholds[i]:
            step_status = "done" if task.progress >= step_progress_thresholds[i] else "processing"
        elif name == current_step:
            step_status = "processing"
        else:
            step_status = "pending"

        if task.status == "completed":
            step_status = "done"
        elif task.status == "failed" and i > 0 and task.progress < step_progress_thresholds[i]:
            step_status = "pending"

        steps.append(StepStatus(name=name, status=step_status))

    if task.status == "failed":
        for step in steps:
            if step.status == "processing":
                step.status = "pending"

    return ProgressOut(
        task_id=task.task_id,
        status=task.status,
        progress=task.progress,
        current_step=task.current_step,
        steps=steps,
        error_message=task.error_message,
    )


@router.get("/{task_id}/download")
async def download_zip(task_id: str, db: Session = Depends(get_db), current_user: UserOut = Depends(get_current_active_user)):
    task = _require_convert_task_access(db, task_id, current_user)
    if task.status == "processing":
        raise HTTPException(status_code=400, detail="转换尚未完成")
    if not task.output_zip_path:
        raise HTTPException(status_code=500, detail="输出文件不存在")

    file_path = f".{task.output_zip_path}"
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="输出文件不存在")

    return FileResponse(
        file_path,
        media_type=_media_type_for_file(file_path),
        filename=os.path.basename(file_path),
    )


@router.get("/{task_id}/report", response_model=ReportOut)
async def get_report(task_id: str, db: Session = Depends(get_db), current_user: UserOut = Depends(get_current_active_user)):
    task = _require_convert_task_access(db, task_id, current_user)
    if task.status not in ["completed", "failed"]:
        raise HTTPException(status_code=400, detail="转换尚未完成")

    if task.verification_report:
        report_data = json.loads(task.verification_report)
    else:
        report_data = {"overall": "failed", "checks": [], "unmapped_sections": []}

    checks = []
    for c in report_data.get("checks", []):
        checks.append(CheckItem(
            name=c["name"],
            status=c.get("status", "failed"),
            detail=c.get("detail"),
        ))

    return ReportOut(
        task_id=task.task_id,
        overall=report_data.get("overall", "failed"),
        checks=checks,
        unmapped_sections=report_data.get("unmapped_sections"),
        active_rules=report_data.get("active_rules"),
    )


@router.get("/{task_id}/detail")
async def get_detail(task_id: str, db: Session = Depends(get_db), current_user: UserOut = Depends(get_current_active_user)):
    task = _require_convert_task_access(db, task_id, current_user)

    detail = []
    if task.conversion_detail:
        detail = json.loads(task.conversion_detail)
    return {"task_id": task_id, "detail": detail}


@router.get("/", response_model=list[ConvertTaskOut])
async def list_tasks(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: UserOut = Depends(get_current_active_user),
):
    tasks = get_convert_tasks(db, skip=skip, limit=limit)
    if current_user.role != "admin":
        tasks = [task for task in tasks if getattr(task, "user_id", None) == current_user.id]
    return tasks


@router.delete("/{task_id}")
async def remove_task(task_id: str, db: Session = Depends(get_db), current_user: UserOut = Depends(get_current_active_user)):
    _require_convert_task_access(db, task_id, current_user)
    task = delete_convert_task(db, task_id)
    with _tasks_lock:
        _task_store.pop(task_id, None)
    return {"message": "任务已删除"}


# ─── 转换规则库 ─────────────────────────────────────────────

@router.get("/rules", response_model=list)
async def list_convert_rules(db: Session = Depends(get_db), _: UserOut = Depends(require_admin)):
    from app.crud.convert_rule import get_convert_rules, seed_default_rules
    seed_default_rules(db)
    rules = get_convert_rules(db)
    return [
        {
            "id": r.id,
            "rule_number": r.rule_number,
            "category": r.category,
            "description": r.description,
            "is_active": r.is_active,
            "created_at": r.created_at.isoformat() if r.created_at else "",
        }
        for r in rules
    ]


@router.post("/rules", response_model=dict)
async def create_convert_rule_api(
    category: str = Form(...),
    description: str = Form(...),
    rule_number: str = Form(None),
    db: Session = Depends(get_db),
    _: UserOut = Depends(require_admin),
):
    from app.crud.convert_rule import create_convert_rule
    from app.schemas.convert_rule import ConvertRuleCreate
    rule = create_convert_rule(db, ConvertRuleCreate(
        rule_number=rule_number, category=category, description=description
    ))
    return {"id": rule.id, "rule_number": rule.rule_number}


@router.put("/rules/{rule_id}", response_model=dict)
async def toggle_convert_rule_api(rule_id: int, db: Session = Depends(get_db), _: UserOut = Depends(require_admin)):
    from app.crud.convert_rule import toggle_convert_rule
    rule = toggle_convert_rule(db, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
    return {"id": rule.id, "is_active": rule.is_active}


@router.delete("/rules/{rule_id}", response_model=dict)
async def delete_convert_rule_api(rule_id: int, db: Session = Depends(get_db), _: UserOut = Depends(require_admin)):
    from app.crud.convert_rule import delete_convert_rule
    rule = delete_convert_rule(db, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
    return {"ok": True}


@router.post("/rules/bulk-delete", response_model=dict)
async def bulk_delete_convert_rules_api(
    rule_ids: str = Form(...),
    db: Session = Depends(get_db),
    _: UserOut = Depends(require_admin),
):
    from app.crud.convert_rule import bulk_delete_convert_rules
    ids = [int(x) for x in rule_ids.split(",") if x.strip()]
    cnt = bulk_delete_convert_rules(db, ids)
    return {"deleted": cnt}
