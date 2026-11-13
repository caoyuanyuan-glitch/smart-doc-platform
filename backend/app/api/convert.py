from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
import csv
import html
import io
import hashlib
import os
import re
import json
import time
import zipfile
import shutil
import threading
import urllib.parse
import xml.etree.ElementTree as ET
import base64
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
from app.utils.convert_verify import verify_output_dir

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
    "关于指南",
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
# Markdown image tokens. Paths may contain parentheses or "&", so do not cut
# at the first ")". Angle-bracket form ![alt](<path>) is preferred.
class _MdImageMatch:
    def __init__(self, alt, href, start, end):
        self.alt = alt
        self.href = href
        self._start = start
        self._end = end

    def group(self, n):
        if n == 0:
            return None
        if n == 1:
            return self.alt
        if n == 2:
            return self.href
        raise IndexError(n)

    def start(self):
        return self._start

    def end(self):
        return self._end


def _parse_md_image_at(text, pos=0):
    """Parse one markdown image at pos. Supports ![alt](<path>) and nested ( )."""
    if not text.startswith("![", pos):
        return None
    rb = text.find("](", pos)
    if rb < 0:
        return None
    alt = text[pos + 2:rb]
    if "\n" in alt:
        return None
    url_start = rb + 2
    if url_start < len(text) and text[url_start] == "<":
        gt = text.find(">", url_start + 1)
        if gt < 0 or gt + 1 >= len(text) or text[gt + 1] != ")":
            return None
        href = html.unescape(text[url_start + 1:gt])
        return _MdImageMatch(alt, href, pos, gt + 2)
    depth = 1
    j = url_start
    while j < len(text):
        ch = text[j]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                href = text[url_start:j]
                if not href or "\n" in href:
                    return None
                return _MdImageMatch(alt, html.unescape(href), pos, j + 1)
        j += 1
    return None


def _match_md_image_line(text):
    """Match a line that is only one markdown image (optional trailing space)."""
    stripped = (text or "").strip()
    match = _parse_md_image_at(stripped, 0)
    if not match or stripped[match.end():].strip():
        return None
    return match


def _iter_md_images(text):
    i = 0
    value = text or ""
    while i < len(value):
        start = value.find("![", i)
        if start < 0:
            return
        match = _parse_md_image_at(value, start)
        if match:
            yield match
            i = match.end()
        else:
            i = start + 2


def _md_image_markup(path, alt=None):
    name = alt if alt is not None else os.path.basename(path or "")
    return f"![{name}](<{path}>)"


def _rewrite_dita_image_hrefs(content, url_map):
    rewritten = content or ""
    for url, local in (url_map or {}).items():
        rewritten = rewritten.replace(
            f'href="{_escape_xml_attr(url)}"',
            f'href="{_escape_xml_attr(local)}"',
        )
    return rewritten


def _rewrite_md_image_hrefs(content, url_map):
    rewritten = content or ""
    for url, local in (url_map or {}).items():
        rewritten = rewritten.replace(f"](<{url}>)", f"](<{local}>)")
        rewritten = rewritten.replace(f"]({url})", f"]({local})")
    return rewritten


def _strip_md_image_tokens(value):
    text = value or ""
    parts = []
    last = 0
    for match in _iter_md_images(text):
        parts.append(text[last:match.start()])
        last = match.end()
    parts.append(text[last:])
    return "".join(parts).strip()


def _stash_md_images(text):
    """Replace markdown images with [[IMG:n]] before XML escaping."""
    store = []
    parts = []
    last = 0
    value = text or ""
    for match in _iter_md_images(value):
        parts.append(value[last:match.start()])
        parts.append(f"[[IMG:{len(store)}]]")
        store.append({"alt": match.group(1), "href": match.group(2)})
        last = match.end()
    parts.append(value[last:])
    return "".join(parts), store


IMG_PLACEHOLDER_RE = re.compile(r"^\[\[IMG:(\d+)\]\]\s*$")
IMG_PLACEHOLDER_ANY_RE = re.compile(r"\[\[IMG:(\d+)\]\]")


ABOUT_MANUAL_SPLIT_RE = re.compile(
    r'(?='
    r'本说明书及其包含的信息'
    r'|本说明书的读者为终端用户'
    r'|华大智造对本说明书不做任何种类的保证'
    r'|华大智造已经采取措施'
    r'|本说明书中的所有图片均为示意图'
    r'|(?:(?<=。 )|(?<=。))[A-Za-z][A-Za-z0-9-]*TM是'
    r'|©'
    r')'
)
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


COVER_PART_NO_RE = re.compile(r'(H-\d{3}-\d{6}-\d{2})', re.I)


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
    cleaned = cleaned.replace("\u2008", "").replace("\u2009", " ")
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    return cleaned.strip()


def _xref_fold_key(title):
    """Collapse whitespace so 读长 DNB matches 读长DNB."""
    text = html.unescape(title or "")
    text = _clean_xref_title(text) or text
    return re.sub(r"\s+", "", text)


TOPIC_ID_RE = re.compile(r"^(?:DTO|CTO|DTC|CTT)\d+")


def _xref_map_put(xref_map, title, tid):
    if xref_map is None or not title or not tid:
        return
    xref_map.setdefault(title, tid)
    cleaned = _clean_xref_title(title)
    if cleaned:
        xref_map.setdefault(cleaned, tid)
    folded = _xref_fold_key(title)
    if folded:
        xref_map.setdefault(folded, tid)


def _xref_map_get(xref_map, title):
    if not xref_map or not title:
        return None
    seen = []
    for key in (title, _clean_xref_title(title), _xref_fold_key(title)):
        if key and key not in seen:
            seen.append(key)
    for key in seen:
        val = xref_map.get(key)
        if val and TOPIC_ID_RE.match(str(val)):
            return val
    return None


def _space_alnum_cjk(text):
    """Insert a space where ASCII letters/digits are followed by CJK.

    Cross-reference link text follows the source layout 第12 页“测定DNB 浓度”.
    """
    return re.sub(r'([A-Za-z0-9])([\u4e00-\u9fff])', r'\1 \2', text or '')


def _xref_visible_inner(display, page, dita_lang):
    """IDML-visible fallback when a cross-reference has no target topic file."""
    title = _space_alnum_cjk(display)
    is_english = str(dita_lang or "").lower().startswith("en")
    if page:
        if is_english:
            return f"{title} on page {page}"
        return f'{_space_alnum_cjk("第" + str(page) + "页")}“{title}”'
    if is_english:
        return title
    return f"“{title}”"


def _escape_xml_text(text):
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


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
        if not _table_grid_is_vertical_header(grid):
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
        "user-supplied equipment",
        "试剂套装组分",
        "组分清单",
        "测序试剂套装",
        "订购信息",
        "有害物质",
        "ordering information",
        "hazardous substance",
        "performing a wash",
        "wash solutions",
        "wash protocol",
    )
    return any(marker in blob for marker in markers)


_dita_mm_width_re = re.compile(r"(?i)^(\d+)\s*mm$")


def _dita_format_mm_width(wide):
    """IME extra-wide tables use outputclass with a spaced unit, e.g. '180 mm'."""
    if not wide:
        return wide
    match = _dita_mm_width_re.match(str(wide).strip())
    if match:
        return f"{match.group(1)} mm"
    return str(wide).strip()


_VERSION_HISTORY_TITLES = {"版本记录", "version history"}
_VERSION_COLUMN_LABELS = {"版本", "version"}
_VERSION_ROW_ORIENTED_HEADERS = {
    "发布日期", "date", "日期", "revision date", "修订日期",
}


def _dita_entry_plain_text(entry_xml):
    text = re.sub(r"<[^>]+>", "", entry_xml or "")
    return (
        text.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .strip()
    )


def _is_version_history_topic(xml_text):
    titles = re.findall(r'cms:title="([^"]+)"', xml_text or "")
    return any(title.strip().lower() in _VERSION_HISTORY_TITLES for title in titles)


def _transpose_version_column_table(xml_text):
    """Turn version-as-column history tables into version-as-row tables."""
    if not xml_text:
        return xml_text
    match = re.search(r"<table\b[\s\S]*?</table>", xml_text)
    if not match:
        return xml_text
    table = match.group(0)
    rows = re.findall(r"<row\b[\s\S]*?</row>", table)
    parsed = []
    for row in rows:
        entries = re.findall(r"<entry\b[^>]*>([\s\S]*?)</entry>", row)
        parsed.append([_dita_entry_plain_text(entry) for entry in entries])
    if len(parsed) < 2 or len(parsed[0]) < 3:
        return xml_text
    header = parsed[0]
    if header[0].strip().lower() not in _VERSION_COLUMN_LABELS:
        return xml_text
    if header[1].strip().lower() in _VERSION_ROW_ORIENTED_HEADERS:
        return xml_text
    version_headers = header[1:]
    if not all(re.match(r"^\d+(\.\d+)*$", cell or "") for cell in version_headers):
        return xml_text

    attr_rows = parsed[1:]
    col_names = ["版本"] + [row[0] for row in attr_rows]

    def _entry_xml(text):
        escaped = (
            (text or "")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        return f"<entry><p>{escaped}</p></entry>"

    new_rows = [col_names]
    for index, version in enumerate(version_headers):
        values = []
        for attr_row in attr_rows:
            values.append(attr_row[index + 1] if index + 1 < len(attr_row) else "")
        new_rows.append([version] + values)

    cols = len(col_names)
    colspecs = "\n".join(
        f'            <colspec colname="COLSPEC{i}" colwidth="1.00*"/>'
        for i in range(cols)
    )
    thead = "              <row>\n" + "\n".join(
        f"                {_entry_xml(cell)}" for cell in new_rows[0]
    ) + "\n              </row>"
    tbody = "\n".join(
        "              <row>\n"
        + "\n".join(f"                {_entry_xml(cell)}" for cell in row)
        + "\n              </row>"
        for row in new_rows[1:]
    )
    new_table = (
        "        <table>\n"
        f'          <tgroup cols="{cols}">\n'
        f"{colspecs}\n"
        f"            <thead>\n{thead}\n            </thead>\n"
        f"            <tbody>\n{tbody}\n            </tbody>\n"
        "          </tgroup>\n"
        "        </table>"
    )
    return xml_text[: match.start()] + new_table + xml_text[match.end():]


def _apply_dita_image_page_widths(output_base, max_width_mm="150mm", min_px=400):
    """Limit large raster screenshots so IME does not overflow the page."""
    image_dir = os.path.join(output_base, "image")
    large_names = set()
    if os.path.isdir(image_dir):
        try:
            from PIL import Image
        except Exception:
            Image = None
        for name in os.listdir(image_dir):
            path = os.path.join(image_dir, name)
            if not os.path.isfile(path) or Image is None:
                continue
            try:
                with Image.open(path) as image:
                    if image.size[0] >= min_px:
                        large_names.add(name)
            except Exception:
                continue
    if not large_names:
        return 0
    updated = 0
    for fname in os.listdir(output_base):
        if not fname.endswith(".dita"):
            continue
        path = os.path.join(output_base, fname)
        text = open(path, encoding="utf-8").read()

        def _inject_width(match):
            tag = match.group(0)
            if re.search(r"\bwidth=", tag):
                return tag
            href_match = re.search(r'href="([^"]+)"', tag)
            if not href_match:
                return tag
            name = os.path.basename(href_match.group(1).replace("\\", "/"))
            if name not in large_names:
                return tag
            if tag.endswith("/>"):
                return tag[:-2] + f' width="{max_width_mm}"/>'
            if tag.endswith(">"):
                return tag[:-1] + f' width="{max_width_mm}">'
            return tag

        new_text = re.sub(r"<image\b[^>]*>", _inject_width, text)
        if new_text != text:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(new_text)
            updated += 1
    return updated


def _fmt_mm(value):
    text = f"{float(value):.1f}"
    if text.endswith(".0"):
        text = text[:-2]
    return f"{text}mm"


def _svg_length_to_mm(raw):
    match = re.match(r"^\s*([\d.]+)\s*(mm|px|pt|cm)?\s*$", raw or "", re.I)
    if not match:
        return None
    value = float(match.group(1))
    unit = (match.group(2) or "").lower()
    if unit == "mm":
        return value
    if unit == "cm":
        return value * 10.0
    if unit == "pt":
        return value * 25.4 / 72.0
    return value * 25.4 / 96.0


def _svg_declared_size_mm(path):
    try:
        text = open(path, encoding="utf-8", errors="ignore").read(12000)
    except Exception:
        return None
    width_match = re.search(r'\bwidth="([^"]+)"', text)
    height_match = re.search(r'\bheight="([^"]+)"', text)
    width = _svg_length_to_mm(width_match.group(1) if width_match else "")
    height = _svg_length_to_mm(height_match.group(1) if height_match else "")
    if width and height and width > 0.5 and height > 0.5:
        return width, height
    return None


def _apply_dita_placed_image_sizes(output_base, size_map=None):
    """Stamp IDML frame sizes (or SVG fallback) onto <image> tags lacking width."""
    lookup = {}
    for key, value in (size_map or {}).items():
        if not value or len(value) < 2:
            continue
        lookup[str(key).lower()] = (float(value[0]), float(value[1]))
    image_dir = os.path.join(output_base or "", "image")
    if not output_base or not os.path.isdir(output_base):
        return 0
    updated = 0
    for fname in os.listdir(output_base):
        if not fname.endswith(".dita"):
            continue
        path = os.path.join(output_base, fname)
        text = open(path, encoding="utf-8").read()

        def _inject_size(match):
            tag = match.group(0)
            if re.search(r"\bwidth=", tag):
                return tag
            href_match = re.search(r'href="([^"]+)"', tag)
            if not href_match:
                return tag
            name = os.path.basename(href_match.group(1).replace("\\", "/"))
            stem = os.path.splitext(name)[0].lower()
            size = lookup.get(stem)
            if not size:
                size = lookup.get(_idml_normalize_image_stem(stem).lower())
            if not size and name.lower().endswith(".svg"):
                svg_path = os.path.join(image_dir, name)
                if os.path.isfile(svg_path):
                    size = _svg_declared_size_mm(svg_path)
            if not size:
                return tag
            attr = f' width="{_fmt_mm(size[0])}" height="{_fmt_mm(size[1])}"'
            if tag.endswith("/>"):
                return tag[:-2] + attr + "/>"
            if tag.endswith(">"):
                return tag[:-1] + attr + ">"
            return tag

        new_text = re.sub(r"<image\b[^>]*>", _inject_size, text)
        if new_text != text:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(new_text)
            updated += 1
    return updated



def _dita_image_basename(tag):
    href_match = re.search(r'href="([^"]+)"', tag or "")
    if not href_match:
        return ""
    return os.path.basename(href_match.group(1).replace("\\", "/")).lower()


def _apply_dita_inline_icon_widths(output_base, size_mm=6.0):
    """Force inline icon_/button_ images to 6 mm so status glyphs stay in line."""
    if not output_base or not os.path.isdir(output_base):
        return 0
    label = _fmt_mm(size_mm)
    updated = 0
    for fname in os.listdir(output_base):
        if not fname.endswith(".dita"):
            continue
        path = os.path.join(output_base, fname)
        text = open(path, encoding="utf-8").read()
        if _is_graphical_symbol_topic(text):
            continue

        def _force_icon(match):
            tag = match.group(0)
            name = _dita_image_basename(tag)
            if not (name.startswith("icon") or name.startswith("button_")):
                return tag
            if re.search(r"\bwidth=", tag):
                tag = re.sub(r'\bwidth="[^"]*"', f'width="{label}"', tag, count=1)
            elif tag.endswith("/>"):
                tag = tag[:-2] + f' width="{label}"/>'
            elif tag.endswith(">"):
                tag = tag[:-1] + f' width="{label}">'
            if re.search(r"\bheight=", tag):
                tag = re.sub(r'\bheight="[^"]*"', f'height="{label}"', tag, count=1)
            return tag

        new_text = re.sub(r"<image\b[^>]*>", _force_icon, text)
        if new_text != text:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(new_text)
            updated += 1
    return updated


def _is_graphical_symbol_topic(xml_text):
    """Symbol-legend topics keep IDML icon sizes instead of the 6 mm inline force."""
    text = xml_text or ""
    if "图形符号" in text:
        return True
    if re.search(r"(?i)graphical symbols?", text):
        return True
    if re.search(r"(?i)symbols on the packaging", text):
        return True
    return bool(
        re.search(
            r'(?i)cms:title="(?:Packaging|包装)"|<title[^>]*>\s*(?:Packaging|包装)\s*<',
            text,
        )
    )


def _parse_dita_mm_attr(value):
    match = re.match(r"^\s*([\d.]+)\s*mm\s*$", str(value or ""), re.I)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _svg_viewbox_aspect(path):
    try:
        text = open(path, encoding="utf-8", errors="ignore").read(20000)
    except Exception:
        return None
    match = re.search(r'viewBox="[\d.+-]+\s+[\d.+-]+\s+([\d.]+)\s+([\d.]+)"', text)
    if not match:
        return None
    width = float(match.group(1))
    height = float(match.group(2))
    if width <= 0 or height <= 0:
        return None
    return height / width


def _rewrite_image_mm(tag, width, height):
    width_attr = _fmt_mm(width)
    height_attr = _fmt_mm(height)
    if re.search(r"\bwidth=", tag):
        tag = re.sub(r'\bwidth="[^"]*"', f'width="{width_attr}"', tag, count=1)
    elif tag.endswith("/>"):
        tag = tag[:-2] + f' width="{width_attr}"/>'
    elif tag.endswith(">"):
        tag = tag[:-1] + f' width="{width_attr}">'
    if re.search(r"\bheight=", tag):
        tag = re.sub(r'\bheight="[^"]*"', f'height="{height_attr}"', tag, count=1)
    elif tag.endswith("/>"):
        tag = tag[:-2] + f' height="{height_attr}"/>'
    elif tag.endswith(">"):
        tag = tag[:-1] + f' height="{height_attr}">'
    return tag


def _apply_dita_flow_and_symbol_sizes(output_base, min_symbol_mm=15.0, min_flow_mm=100.0):
    """Enlarge packaging symbols and un-squash cropped flow diagrams."""
    if not output_base or not os.path.isdir(output_base):
        return 0
    image_dir = os.path.join(output_base, "image")
    updated = 0
    for fname in os.listdir(output_base):
        if not fname.endswith(".dita"):
            continue
        path = os.path.join(output_base, fname)
        text = open(path, encoding="utf-8").read()
        is_symbol_topic = _is_graphical_symbol_topic(text)

        def _tune(match):
            tag = match.group(0)
            name = _dita_image_basename(tag)
            width_match = re.search(r'\bwidth="([^"]+)"', tag)
            height_match = re.search(r'\bheight="([^"]+)"', tag)
            width = _parse_dita_mm_attr(width_match.group(1) if width_match else "")
            height = _parse_dita_mm_attr(height_match.group(1) if height_match else "")
            if name.startswith("flow_"):
                aspect = None
                href_match = re.search(r'href="([^"]+)"', tag)
                if href_match:
                    svg_name = os.path.basename(href_match.group(1).replace("\\", "/"))
                    svg_path = os.path.join(image_dir, svg_name)
                    if svg_path.lower().endswith(".svg") and os.path.isfile(svg_path):
                        aspect = _svg_viewbox_aspect(svg_path)
                if aspect is None and width and height and width > 0:
                    aspect = height / width
                new_w = max(width or 0.0, min_flow_mm)
                new_h = new_w * aspect if aspect else (height or new_w * 0.3)
                return _rewrite_image_mm(tag, new_w, new_h)
            if is_symbol_topic and width and height:
                long_side = max(width, height)
                if 0 < long_side < min_symbol_mm:
                    scale = min_symbol_mm / long_side
                    return _rewrite_image_mm(tag, width * scale, height * scale)
            return tag

        new_text = re.sub(r"<image\b[^>]*>", _tune, text)
        if new_text != text:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(new_text)
            updated += 1
    return updated


def _apply_dita_overflow_image_widths(output_base, max_width_mm=143.0, min_width_mm=170.0):
    """Clamp overflowing screenshot figures to 143 mm so IME stays on the page."""
    if not output_base or not os.path.isdir(output_base):
        return 0
    updated = 0
    max_label = _dita_format_mm_width(f"{int(max_width_mm)}mm")
    for fname in os.listdir(output_base):
        if not fname.endswith(".dita"):
            continue
        path = os.path.join(output_base, fname)
        text = open(path, encoding="utf-8").read()

        def _clamp(match):
            tag = match.group(0)
            width_match = re.search(r'\bwidth="([^"]+)"', tag)
            if not width_match:
                return tag
            width = _parse_dita_mm_attr(width_match.group(1))
            if width is None or width < min_width_mm:
                return tag
            scale = max_width_mm / width
            tag = re.sub(r'\bwidth="[^"]*"', f'width="{max_label}"', tag, count=1)
            height_match = re.search(r'\bheight="([^"]+)"', tag)
            if height_match:
                height = _parse_dita_mm_attr(height_match.group(1))
                if height:
                    tag = re.sub(
                        r'\bheight="[^"]*"',
                        f'height="{_fmt_mm(height * scale)}"',
                        tag,
                        count=1,
                    )
            return tag

        new_text = re.sub(r"<image\b[^>]*>", _clamp, text)
        if new_text != text:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(new_text)
            updated += 1
    return updated


def _is_about_manual_topic(xml_text):
    titles = re.findall(r'cms:title="([^"]+)"', xml_text or "")
    if any(title.strip() == "关于说明书" for title in titles):
        return True
    return bool(re.search(r"<title[^>]*>\s*关于说明书\s*</title>", xml_text or ""))


def _split_about_manual_paragraphs(xml_text):
    """Restore 关于说明书 logical paragraphs that were collapsed into one <p>."""
    if not xml_text or not _is_about_manual_topic(xml_text):
        return xml_text

    def _split_p(match):
        inner = (match.group(1) or "").strip()
        if not ABOUT_MANUAL_SPLIT_RE.search(inner):
            return match.group(0)
        parts = [part.strip() for part in ABOUT_MANUAL_SPLIT_RE.split(inner) if part.strip()]
        if len(parts) < 2:
            return match.group(0)
        indent = re.match(r"^[ \t]*", match.group(0)).group(0)
        return "\n".join(f"{indent}<p>{part}</p>" for part in parts)

    return re.sub(r"<p>([^<]+)</p>", _split_p, xml_text)


def _wrap_standalone_dita_images_in_fig(xml_text):
    """Wrap block-level <image> tags in <fig>; leave inline icons in <p>/<entry>."""
    if not xml_text:
        return xml_text
    lines = xml_text.split("\n")
    wrapped = []
    image_line_re = re.compile(r"^([ \t]*)(<image\b[^>]*>\s*</image>|<image\b[^>]*/>)\s*$")
    for line in lines:
        match = image_line_re.match(line)
        if match and "<fig>" not in line:
            wrapped.append(f"{match.group(1)}<fig>{match.group(2)}</fig>")
        else:
            wrapped.append(line)
    return "\n".join(wrapped)


def _dita_fig_is_screenshot(fig_xml):
    href_match = re.search(r'href="([^"]+)"', fig_xml or "")
    if not href_match:
        return False
    name = os.path.basename(href_match.group(1).replace("\\", "/")).lower()
    if name.startswith(("icon", "button_", "formula", "label")):
        return False
    width_match = re.search(r'\bwidth="([^"]+)"', fig_xml or "")
    width = _parse_dita_mm_attr(width_match.group(1) if width_match else "")
    if width is not None and width < 40:
        return False
    return True


def _dita_fig_image_xml(fig_xml):
    match = re.search(r"(<image\b[^>]*>\s*</image>|<image\b[^>]*/>)", fig_xml or "")
    return match.group(1) if match else ""


def _dita_fig_title_xml(fig_xml):
    match = re.search(r"<title\b[^>]*>(.*?)</title>", fig_xml or "", re.S)
    return (match.group(1) or "").strip() if match else ""


def _dita_fig_inner_tables(fig_xml):
    return re.findall(r"<table\b[\s\S]*?</table>", fig_xml or "")


def _pair_adjacent_dita_figures(xml_text):
    """Wrap two consecutive untitled screenshot <fig>s in a headerless 1-row 2-col table.

    Figs that already have a <title> stay as independent figures so IME keeps
    the caption. Side-by-side screenshots that originated as IDML tables are
    already tables and do not go through this pass.
    """
    if not xml_text:
        return xml_text
    # Each fig must stop at its own </fig>. A non-greedy <fig>.*?</fig> still
    # backtracks across later figures until the next fig is whitespace-adjacent,
    # which swallows list items and unbalances tags.
    single_fig = r"<fig\b[^>]*>(?:(?!</fig>)[\s\S])*</fig>"
    fig_pair_re = re.compile(rf"({single_fig})(\s*)({single_fig})")

    def _inside_table_or_entry(prefix):
        return (
            prefix.rfind("<entry>") > prefix.rfind("</entry>")
            or prefix.rfind("<table") > prefix.rfind("</table>")
        )

    pos = 0
    while True:
        match = fig_pair_re.search(xml_text, pos)
        if not match:
            break
        prefix = xml_text[: match.start()]
        fig1, fig2 = match.group(1), match.group(3)
        img1 = _dita_fig_image_xml(fig1)
        img2 = _dita_fig_image_xml(fig2)
        title1 = _dita_fig_title_xml(fig1)
        title2 = _dita_fig_title_xml(fig2)
        titled_count = int(bool(title1)) + int(bool(title2))
        mixed_title = titled_count == 1
        if (
            _inside_table_or_entry(prefix)
            or not img1
            or not img2
            or titled_count == 2
            or (
                not mixed_title
                and not (
                    _dita_fig_is_screenshot(fig1) and _dita_fig_is_screenshot(fig2)
                )
            )
        ):
            pos = match.start() + len(fig1)
            continue
        indent = "        "
        table_title = title1 or title2
        title_xml = f"{indent}  <title>{table_title}</title>\n" if table_title else ""
        cell_bg = ' vf:bgcolor="#FFFFFF"' if table_title else ""
        inner_tables = _dita_fig_inner_tables(fig1) + _dita_fig_inner_tables(fig2)
        table = (
            f"{indent}<table>\n"
            f"{title_xml}"
            f"{indent}  <tgroup cols=\"2\">\n"
            f"{indent}    <colspec colname=\"COLSPEC0\" colwidth=\"0.50*\"/>\n"
            f"{indent}    <colspec colname=\"COLSPEC1\" colwidth=\"0.50*\"/>\n"
            f"{indent}    <tbody>\n"
            f"{indent}      <row>\n"
            f"{indent}        <entry valign=\"bottom\"{cell_bg}><p>{img1}</p></entry>\n"
            f"{indent}        <entry valign=\"bottom\"{cell_bg}><p>{img2}</p></entry>\n"
            f"{indent}      </row>\n"
            f"{indent}    </tbody>\n"
            f"{indent}  </tgroup>\n"
            f"{indent}</table>"
        )
        if inner_tables:
            fig_title = f"{indent}  <title>{table_title}</title>\n" if table_title else ""
            tables_xml = "".join(
                tbl if tbl.endswith("\n") else tbl + "\n" for tbl in inner_tables
            )
            replacement = (
                f"{indent}<fig>\n"
                f"{fig_title}"
                f"{indent}  {img1}\n"
                f"{indent}  {img2}\n"
                f"{tables_xml}"
                f"{indent}</fig>"
            )
        else:
            replacement = table
        xml_text = xml_text[: match.start()] + replacement + xml_text[match.end():]
        pos = match.start() + len(replacement)
    return xml_text


def _align_side_by_side_figure_entries(xml_text):
    """Bottom-align entries in 2-col tables that hold figures.

    Side-by-side screenshots often differ in height; without valign the
    captions sit at different rows.
    """
    if not xml_text or "<fig>" not in xml_text:
        return xml_text

    def _table_repl(match):
        table = match.group(0)
        if "<fig>" not in table:
            return table
        if not re.search(r'<tgroup\b[^>]*\bcols="2"', table):
            return table

        def _entry_open(ematch):
            tag = ematch.group(0)
            if "valign=" in tag:
                return tag
            if tag.endswith("/>"):
                return f'{tag[:-2]} valign="bottom"/>'
            return f'{tag[:-1]} valign="bottom">'

        return re.sub(r"<entry\b[^>]*/?>", _entry_open, table)

    return re.sub(r"<table\b[^>]*>.*?</table>", _table_repl, xml_text, flags=re.S)


def _wrap_noteish_top_level_lists(xml_text):
    """Wrap a leading body <ul> that is actually a Word 提示/注意 box."""
    if not xml_text:
        return xml_text
    body_match = re.search(
        r"(<(?:body|conbody)\b[^>]*>)([\s\S]*?)(</(?:body|conbody)>)",
        xml_text,
    )
    if not body_match:
        return xml_text
    body = body_match.group(2)
    if re.match(r"\s*<note\b", body):
        return xml_text
    ul_match = re.match(r"\s*(<ul>[\s\S]*?</ul>)", body)
    if not ul_match:
        return xml_text
    ul = ul_match.group(1)
    if not re.search(
        r"严禁混用|请将组分存放|仅用于科研用途|不可用于临床诊断",
        ul,
    ):
        return xml_text
    wrapped = f"\n        <note type=\"tip\">\n{ul}\n        </note>"
    new_body = body[: ul_match.start()] + wrapped + body[ul_match.end() :]
    return xml_text[: body_match.start(2)] + new_body + xml_text[body_match.end(2) :]


def _dita_files_in_map_order(output_base):
    ordered = []
    seen = set()
    if not output_base or not os.path.isdir(output_base):
        return ordered
    maps = [name for name in os.listdir(output_base) if name.endswith(".ditamap")]
    if maps:
        text = open(os.path.join(output_base, maps[0]), encoding="utf-8").read()
        for href in re.findall(r'href="([^"]+\.dita)"', text):
            if href in seen:
                continue
            path = os.path.join(output_base, href)
            if os.path.isfile(path):
                ordered.append(path)
                seen.add(href)
    for name in sorted(os.listdir(output_base)):
        if name.endswith(".dita") and name not in seen:
            ordered.append(os.path.join(output_base, name))
            seen.add(name)
    return ordered


def _caption_xref_kind(title):
    text = re.sub(r"\s+", " ", html.unescape(title or "")).strip()
    if re.match(r"^(?:表|Table)\s*\d+", text, re.I):
        return "table"
    if re.match(r"^(?:图|Figure)\s*\d+", text, re.I):
        return "fig"
    return None


def _dita_inner_text(xml_inner):
    return html.unescape(re.sub(r"<[^>]+>", "", xml_inner or "")).strip()


def _empty_cms_xref_xml(href, title, keyref="", xref_id=""):
    attrs = []
    if href:
        attrs.append(f'href="{_escape_xml_attr(href)}"')
    if keyref:
        attrs.append(f'keyref="{_escape_xml_attr(keyref)}"')
    attrs.append(f'cms:title="{_escape_xml_attr(title)}"')
    if xref_id:
        attrs.append(f'id="{_escape_xml_attr(xref_id)}"')
    return "<xref " + " ".join(attrs) + "/>"


def _topic_id_from_dita_href(href):
    if not href:
        return ""
    stem = os.path.splitext(os.path.basename(href.split("#", 1)[0].strip()))[0]
    if re.match(r"^[A-Za-z]{3}\d+$", stem):
        return stem
    return ""


def _ime_xref_href(filename, root_id, elem_id):
    """IME href is file.dita#topic-id/title-id, never keyref."""
    if filename and root_id and elem_id:
        return f"{filename}#{root_id}/{elem_id}"
    if filename and elem_id:
        return f"{filename}#{elem_id}"
    return filename or ""


def _dita_topic_ids(xml_text):
    root = re.search(r"<(?:topic|concept)\b([^>]*)>", xml_text or "")
    title = re.search(r"<title\b([^>]*)>", xml_text or "")
    return (
        _xml_open_tag_id(root.group(1) if root else ""),
        _xml_open_tag_id(title.group(1) if title else ""),
    )


DITA_XREF_EL_RE = re.compile(
    r"<xref\b[^>]*cms:title=\"[^\"]+\"[^>]*(?:/>|>.*?</xref>)",
    re.S,
)
DITA_FIG_TITLE_RE = re.compile(
    r"<fig\b([^>]*)>\s*<title\b([^>]*)>(.*?)</title>",
    re.S,
)
DITA_TABLE_TITLE_RE = re.compile(
    r"<table\b[^>]*>\s*<title\b([^>]*)>(.*?)</title>",
    re.S,
)


def _xml_open_tag_id(tag_or_attrs):
    match = re.search(r'\bid="([^"]+)"', tag_or_attrs or "")
    return match.group(1) if match else ""


def _ime_style_id(prefix, topic_id, serial):
    """IME indexes fig/table/title/image as 3-letter prefix + 8 hex digits."""
    seed = f"{prefix}:{topic_id}:{serial}".encode("utf-8")
    return f"{prefix}{hashlib.md5(seed).hexdigest()[:8]}"


def _stamp_xml_open_id(open_tag, element_id):
    if not open_tag or not element_id or _xml_open_tag_id(open_tag):
        return open_tag
    if open_tag.endswith("/>"):
        return f'{open_tag[:-2]} id="{element_id}"/>'
    if open_tag.endswith(">"):
        return f'{open_tag[:-1]} id="{element_id}">'
    return open_tag


def _assign_dita_caption_ids(xml_text, topic_id):
    """IME's xref picker only lists nodes that already have id.

    Stamp <fig>, <table>, and their caption <title> so authors can expand
    table/title or fig/title after searching the host topic number.
    Use IME-native ids (fig/tab/tit/ima + 8 hex), and stamp <image> inside fig.
    """
    if not xml_text or not topic_id:
        return xml_text
    counter = [0]

    def _next_id(prefix):
        counter[0] += 1
        return _ime_style_id(prefix, topic_id, counter[0])

    def _fig_open(match):
        return _stamp_xml_open_id(match.group(0), _next_id("fig"))

    xml_text = re.sub(r"<fig\b[^>]*>", _fig_open, xml_text)

    def _fig_title(match):
        return match.group(1) + _stamp_xml_open_id(match.group(2), _next_id("tit"))

    xml_text = re.sub(
        r"(<fig\b[^>]*>\s*)(<title\b[^>]*>)",
        _fig_title,
        xml_text,
    )

    def _stamp_fig_images(match):
        open_tag, inner, close_tag = match.group(1), match.group(2), match.group(3)

        def _img_open(img_match):
            return _stamp_xml_open_id(img_match.group(0), _next_id("ima"))

        inner = re.sub(r"<image\b[^>]*/?>", _img_open, inner)
        return open_tag + inner + close_tag

    xml_text = re.sub(
        r"(<fig\b[^>]*>)([\s\S]*?)(</fig>)",
        _stamp_fig_images,
        xml_text,
    )

    def _table_open(match):
        return _stamp_xml_open_id(match.group(0), _next_id("tab"))

    xml_text = re.sub(r"<table\b[^>]*>", _table_open, xml_text)

    def _table_title(match):
        return match.group(1) + _stamp_xml_open_id(match.group(2), _next_id("tit"))

    xml_text = re.sub(
        r"(<table\b[^>]*>\s*)(<title\b[^>]*>)",
        _table_title,
        xml_text,
    )
    return xml_text


def _pick_caption_target(title, src_filename, caption_index, file_order):
    folded = _xref_fold_key(title)
    candidates = caption_index.get(title) or caption_index.get(folded) or []
    if not candidates:
        return None
    same_file = [item for item in candidates if item[0] == src_filename]
    if same_file:
        return same_file[0]
    try:
        src_pos = file_order.index(src_filename)
    except ValueError:
        src_pos = -1
    later = []
    if src_pos >= 0:
        for filename, elem_id in candidates:
            try:
                if file_order.index(filename) > src_pos:
                    later.append((filename, elem_id))
            except ValueError:
                continue
    if later:
        return later[0]
    return candidates[0]


def _rewrite_caption_xrefs(output_base):
    """Bind 图 N / 表 N xrefs to the next titled fig/table in document order."""
    files = _dita_files_in_map_order(output_base)
    if not files:
        return 0
    events = []
    texts = []
    caption_titles = set()
    caption_index = {}
    file_order = [os.path.basename(path) for path in files]
    for file_idx, path in enumerate(files):
        text = open(path, encoding="utf-8").read()
        texts.append(text)
        items = []
        for match in DITA_XREF_EL_RE.finditer(text):
            cms = re.search(r'cms:title="([^"]*)"', match.group(0))
            if not cms:
                continue
            kind = _caption_xref_kind(html.unescape(cms.group(1)))
            if kind:
                items.append((match.start(), f"{kind}_xref", match.group(0)))
        for match in DITA_FIG_TITLE_RE.finditer(text):
            title = _dita_inner_text(match.group(3))
            if title:
                items.append((match.start(), "fig", title))
                caption_titles.add(title)
                elem_id = _xml_open_tag_id(match.group(2)) or _xml_open_tag_id(match.group(1))
                if elem_id:
                    filename = os.path.basename(path)
                    caption_index.setdefault(title, []).append((filename, elem_id))
                    folded = _xref_fold_key(title)
                    if folded != title:
                        caption_index.setdefault(folded, []).append((filename, elem_id))
        for match in DITA_TABLE_TITLE_RE.finditer(text):
            title = _dita_inner_text(match.group(2))
            if title:
                items.append((match.start(), "table", title))
                caption_titles.add(title)
                elem_id = _xml_open_tag_id(match.group(1))
                if elem_id:
                    filename = os.path.basename(path)
                    caption_index.setdefault(title, []).append((filename, elem_id))
                    folded = _xref_fold_key(title)
                    if folded != title:
                        caption_index.setdefault(folded, []).append((filename, elem_id))
        items.sort(key=lambda item: item[0])
        for _, kind, payload in items:
            events.append((kind, file_idx, payload))

    file_meta = {
        os.path.basename(path): _dita_topic_ids(text)
        for path, text in zip(files, texts)
    }
    fig_q = []
    table_q = []
    replacements = {}
    for kind, file_idx, payload in events:
        if kind == "fig_xref":
            fig_q.append((file_idx, payload))
        elif kind == "table_xref":
            table_q.append((file_idx, payload))
        elif kind == "fig" and fig_q:
            src_idx, xref_xml = fig_q.pop(0)
            replacements.setdefault(src_idx, []).append(
                (xref_xml, _empty_cms_xref_xml("", payload))
            )
        elif kind == "table" and table_q:
            src_idx, xref_xml = table_q.pop(0)
            replacements.setdefault(src_idx, []).append(
                (xref_xml, _empty_cms_xref_xml("", payload))
            )

    updated = 0
    for file_idx, path in enumerate(files):
        text = texts[file_idx]
        for old, new in replacements.get(file_idx, []):
            if old in text:
                text = text.replace(old, new, 1)
        new_text = _empty_dita_xref_inners(
            _stamp_dita_xref_ids(
                _bind_topic_xref_hrefs(
                    _bind_caption_xref_hrefs(
                        text,
                        caption_index,
                        os.path.basename(path),
                        file_order,
                        file_meta,
                    ),
                    file_meta,
                ),
                os.path.splitext(os.path.basename(path))[0],
            )
        )
        if new_text != texts[file_idx]:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(new_text)
            updated += 1
    return updated


def _bind_caption_xref_hrefs(xml_text, caption_index, src_filename, file_order, file_meta=None):
    """Point fig/table xrefs at IME path file.dita#topic-id/title-id."""
    if not xml_text or not caption_index:
        return xml_text

    def _repl(match):
        cms = re.search(r'cms:title="([^"]*)"', match.group(0))
        if not cms:
            return match.group(0)
        title = html.unescape(cms.group(1))
        hit = _pick_caption_target(title, src_filename, caption_index, file_order)
        if not hit:
            return match.group(0)
        filename, elem_id = hit
        root_id = ((file_meta or {}).get(filename) or ("", ""))[0]
        href = _ime_xref_href(filename, root_id, elem_id)
        return _empty_cms_xref_xml(href, title)

    return DITA_XREF_EL_RE.sub(_repl, xml_text)


def _bind_topic_xref_hrefs(xml_text, file_meta):
    """Chapter/section xrefs use file.dita#topic-id/title-id, matching IME packages."""
    if not xml_text or not file_meta:
        return xml_text

    def _repl(match):
        cms = re.search(r'cms:title="([^"]*)"', match.group(0))
        if not cms:
            return match.group(0)
        title = html.unescape(cms.group(1))
        href_m = re.search(r'href="([^"]*)"', match.group(0))
        href = href_m.group(1) if href_m else ""
        if not href:
            return match.group(0)
        filepart, _, frag = href.partition("#")
        if "/" in frag:
            return match.group(0)
        filename = os.path.basename(filepart)
        if not filename.endswith(".dita"):
            return match.group(0)
        meta = file_meta.get(filename)
        if not meta:
            return match.group(0)
        root_id, title_id = meta
        elem_id = frag or title_id
        if not root_id or not elem_id:
            return match.group(0)
        return _empty_cms_xref_xml(_ime_xref_href(filename, root_id, elem_id), title)

    return DITA_XREF_EL_RE.sub(_repl, xml_text)


def _stamp_dita_xref_ids(xml_text, topic_id):
    """Stamp IME-style xref ids. Never write keyref (IME publish treats it as a live key)."""
    if not xml_text:
        return xml_text
    counter = [0]

    def _repl(match):
        xml = match.group(0)
        cms = re.search(r'cms:title="([^"]*)"', xml)
        if not cms:
            return xml
        title = html.unescape(cms.group(1))
        href_m = re.search(r'href="([^"]*)"', xml)
        href = href_m.group(1) if href_m else ""
        xref_id = _xml_open_tag_id(xml)
        if not xref_id:
            counter[0] += 1
            xref_id = _ime_style_id("xre", topic_id or "xref", counter[0])
        return _empty_cms_xref_xml(href, title, xref_id=xref_id)

    return DITA_XREF_EL_RE.sub(_repl, xml_text)


def _empty_dita_xref_inners(xml_text):
    """IME quotes xref inner text; cms:title xrefs stay empty."""

    def _repl(match):
        attrs = match.group(1)
        if "cms:title=" not in attrs:
            return match.group(0)
        attrs = attrs.rstrip()
        if attrs.endswith("/"):
            return match.group(0)
        return f"<xref{attrs}/>"

    return re.sub(
        r"<xref\b([^>]*?)(?:/>|>(?:(?!</xref>).)*</xref>)",
        _repl,
        xml_text or "",
        flags=re.S,
    )


def _postprocess_dita_topics(output_base):
    if not output_base or not os.path.isdir(output_base):
        return 0
    updated = 0
    for fname in os.listdir(output_base):
        if not fname.endswith(".dita"):
            continue
        path = os.path.join(output_base, fname)
        text = open(path, encoding="utf-8").read()
        new_text = _split_about_manual_paragraphs(text)
        new_text = _wrap_noteish_top_level_lists(new_text)
        new_text = _wrap_standalone_dita_images_in_fig(new_text)
        new_text = _pair_adjacent_dita_figures(new_text)
        new_text = _align_side_by_side_figure_entries(new_text)
        new_text = _place_indexterms_in_body(new_text)
        new_text = _assign_dita_caption_ids(new_text, os.path.splitext(fname)[0])
        if new_text != text:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(new_text)
            updated += 1
    updated += _rewrite_caption_xrefs(output_base)
    return updated


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
    token = _md_image_markup(image_path)
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
                        inline_parts.append(_md_image_markup(value))
                        continue
                elif is_unknown_size:
                    if is_note_text:
                        continue
                    if text and not is_caption_text:
                        inline_parts.append(_md_image_markup(value))
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
                    lines.append(_md_image_markup(image_path))
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
                    lines.append(_md_image_markup(image_path))
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
    markdown_text = _idml_insert_precautions_heading(markdown_text)
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


def _load_source_content(source_format, file_path, source_content=""):
    if (source_content or "").strip():
        return source_content
    if not file_path or not os.path.exists(file_path):
        return source_content or ""
    if source_format in ("md", "csv"):
        with open(file_path, "r", encoding="utf-8", errors="ignore") as handle:
            return handle.read()
    if source_format == "docx":
        return _docx_to_markdown(file_path)
    if source_format == "idml":
        return _idml_to_markdown(file_path)
    return source_content or ""


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
        "about the sequencing set",
        "about this guide",
        "about the guide",
        "revision history",
        "version history",
        "manufacturer information",
    }:
        return True
    return bool(re.search(r'关于说明书|关于指南|版本记录|版本历史|试剂盒基本信息|试剂套装基本信息', _clean_title(title or "")))


def _is_index_title(title):
    """True when the heading is the generated Index / 索引 chapter."""
    key = _normalize_section_key(title)
    return key in {"索引", "index"}


def _is_about_manual_title(title):
    key = _normalize_section_key(title)
    if key in {
        "about the user manual",
        "about the instructions for use",
        "about this guide",
        "about the guide",
    }:
        return True
    return bool(re.search(r'关于说明书|关于指南', _clean_title(title or "")))


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
        # IDML list items carry [[LVL:n]] before the markdown marker. After
        # _clean_navtitle the dash remains; neither form is a subheading.
        or first_line.startswith(("[[LVL:", "[[KEEP]]"))
        or re.match(r'^[-*+]\s+', normalized_line)
        or TABLE_CAPTION_PREFIX_RE.match(normalized_line)
        or FIGURE_CAPTION_PREFIX_RE.match(normalized_line)
        # Table group labels such as "测序仪：MGISEQ-2000RS" are body text.
        or re.search(r'[:：]', normalized_line)
        or re.match(r'^(试剂|样本|步骤|操作|注意|提示|警告|小心|请勿|切勿)[:：]', normalized_line)
        or re.search(r'[.!?;:：，。)]$', normalized_line)
        # Index letter headings ("B", "C") are body grouping labels.
        or re.fullmatch(r'[A-Za-z]', normalized_line)
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
    for match in _iter_md_images(content or ""):
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
# (the .ai -> .svg conversion is done outside this pipeline). Raster siblings
# cover source packages that only shipped a JPEG/PNG stand-in.
IDML_DEFERRED_IMAGE_REPLACEMENTS = {
    ".ai": (".svg", ".jpg", ".jpeg", ".png"),
    ".eps": (".svg", ".jpg", ".jpeg", ".png"),
}

IDML_EXTRA_WIDE_TABLE_PT = 480.0


def _idml_deferred_replacements(ext):
    value = IDML_DEFERRED_IMAGE_REPLACEMENTS.get((ext or "").lower())
    if not value:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(value)


def _idml_normalize_image_stem(stem):
    """Drop SVG-pack / InDesign export suffixes such as _g99_32 or -01."""
    text = (stem or "").strip()
    variant_suffix = re.compile(r"(?i)(?:[_-]g\d+(?:[_-]\d+)*|[-_]0[1-9]\d*)$")
    while True:
        stripped = variant_suffix.sub("", text)
        if stripped == text:
            return text
        text = stripped


def _idml_image_candidate_names(base_name):
    """IME-ready filenames to try for an IDML Link basename."""
    stem, ext = os.path.splitext(base_name or "")
    ext_low = ext.lower()
    names = []
    if ext_low in IDML_IME_IMAGE_EXTS:
        names.append(base_name)
    else:
        for replacement in _idml_deferred_replacements(ext_low):
            names.append(f"{stem}{replacement}")
    alt_stem = re.sub(r"[_\s]+\d+$", "", stem)
    if alt_stem and alt_stem.lower() != stem.lower():
        extras = []
        for name in names:
            extras.append(alt_stem + os.path.splitext(name)[1])
        names.extend(extras)
    extras = []
    for name in names:
        name_stem, name_ext = os.path.splitext(name)
        normalized = _idml_normalize_image_stem(name_stem)
        if normalized and normalized.lower() != name_stem.lower():
            extras.append(normalized + name_ext)
    names.extend(extras)
    seen = set()
    unique = []
    for name in names:
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(name)
    return unique


# Real-world IDML style vocabularies (e.g. MGI/DNBSEQ manuals) name headings
# "<group>:Title-L<n>-<lang>" instead of Word's "Heading n". The "<group>"
# prefix varies ("For reagent kit only:", "Operation guide:", ...), so match
# on the "Title-L<level>" token.
IDML_HEADING_LEVEL_RE = re.compile(r'(?i)\bTitle[-:.]?L\s*(\d)\b')

# Front-matter / appendix titles that are level-1 headings without an "L<n>".
IDML_FRONT_TITLE_RE = re.compile(r'(?i)(Title in first page|Title[-:]Appen)')

# Table-of-contents styles; the target DITA package regenerates its own TOC.
IDML_TOC_STYLE_RE = re.compile(r'(?i)^(?:toc|contents)\b')

# Running headers/footers and blank-page markers carry no body content.
IDML_JUNK_STYLE_RE = re.compile(
    r'(?i)(\bheader\b|\bfooter\b|blank[ _]?page|normalparagraphstyle)'
)

# Appendix headings use a "Title-Appen. n" style; tag them so the bookmap
# builder emits an <appendix> container with the original navtitle.
IDML_APPENDIX_STYLE_RE = re.compile(r'(?i)Title[-:]Appen')
IDML_APPENDIX_MARKER = "[[APPENDIX]]"

# Callout boxes ("warning", "tip") come from tables whose cell styles describe
# a single sentence, a warning sentence, a tip or a symbol.
IDML_CALLOUT_STYLE_RE = re.compile(r'(?i)(single\s+sentence|warning\s+sentence|tips?|symbols)')
IDML_CALLOUT_MARKER_RE = re.compile(r'^\[\[NOTE:(\w+)\]\]$')

# Figure captions carry a "Figure-title" paragraph style. They are tagged so
# that the caption can be wrapped together with its image as
# <fig><title>...</title><image/></fig>; IME generates the figure number.
IDML_FIGURE_TITLE_RE = re.compile(r'(?i)Figure[-:]Title')
IDML_FIGCAP_MARKER = "[[FIGCAP]]"

# Table captions carry a "Table-title" paragraph style. They are tagged so the
# DITA layer lifts them into <table><title>...</title>; IME generates the
# "表 N" / "Table N" number.
IDML_TABLE_TITLE_RE = re.compile(r'(?i)(?:Table[-:]Title|Table[-:]Table title|Table-title)')
IDML_TABCAP_MARKER = "[[TABCAP]]"

# Table cells that use a bullet/number paragraph style carry a compact list
# marker through markdown (GFM cells cannot nest lists) so the DITA layer can
# rebuild <ul>/<ol> inside <entry>.
IDML_CELL_UL_OPEN = "[[UL]]"
IDML_CELL_OL_OPEN = "[[OL]]"
IDML_CELL_LIST_SEP = "[[LI]]"
IDML_CELL_UL_CLOSE = "[[/UL]]"
IDML_CELL_OL_CLOSE = "[[/OL]]"
IDML_CELL_P_SEP = "[[P]]"
IDML_INLINE_MARK_STRIP_RE = re.compile(
    r"\[\[(?:/?UI|/?B|/?I|/?TERM|/?SUP|/?SUB|INDEX:[^\]]+)\]\]"
)
_IDML_REGULATION_ID_RE = re.compile(
    r"^(IEC|ISO|EN|GB(?:/T)?|YY|WS|ASTM|UL|CSA|JIS)\s*[\dA-Z]"
)
_IDML_REGULATION_SPLIT_RE = re.compile(
    r"^((?:IEC|ISO|EN|GB(?:/T)?|YY|WS|ASTM|UL|CSA|JIS)\s*[\dA-Z][\w.\-:]*(?:\s+\d{4})?)\s+(.+)$"
)

_IDML_REGULATION_YEAR_RE = re.compile(r"^\d{4}$")

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
IDML_UI_STYLE_RE = re.compile(r'(?i)silk[\s-]*screen')
IDML_UI_MARK_OPEN = "[[UI]]"
IDML_UI_MARK_CLOSE = "[[/UI]]"

# Italic character styles in 617: Cross reference* (N/c/V, book titles) and
# Subtle Emphasis (FontStyle Italic). UI styles take precedence.
IDML_ITALIC_STYLE_RE = re.compile(r'(?i)italic|subtle\s*emphasis|^cross\s*reference')
IDML_I_MARK_OPEN = "[[I]]"
IDML_I_MARK_CLOSE = "[[/I]]"

# Blue reagent names (character style "Reagent name_EN") map to DITA <term>.
IDML_TERM_STYLE_RE = re.compile(r'(?i)reagent\s*name')
IDML_TERM_MARK_OPEN = "[[TERM]]"
IDML_TERM_MARK_CLOSE = "[[/TERM]]"
IDML_NESTED_NOTE_RE = re.compile(r'\[\[NOTE:(\w+)\]\](.*?)\[\[/NOTE\]\]', re.S)

# Superscript character styles (and Position="Superscript") map to DITA <sup>.
IDML_SUP_STYLE_RE = re.compile(r'(?i)superscript')

# Introductory-sentence paragraph styles keep their source line breaks in IME.
IDML_KEEP_STYLE_RE = re.compile(r'(?i)introductory\s+sentence')
IDML_KEEP_MARKER = "[[KEEP]]"

# Cell fill travels as [[BG:#RRGGBB]] so the DITA layer can emit vf:bgcolor.
IDML_BG_MARK_RE = re.compile(r'\[\[BG:(#[0-9A-Fa-f]{6})\]\]')
IDML_CMYK_COLOR_RE = re.compile(
    r'(?i)C\s*=\s*([\d.]+)\s*M\s*=\s*([\d.]+)\s*Y\s*=\s*([\d.]+)\s*K\s*=\s*([\d.]+)'
)
IDML_COMPACT_CMYK_RE = re.compile(
    r'(?i)c(\d+(?:\.\d+)?)m(\d+(?:\.\d+)?)y(\d+(?:\.\d+)?)k(\d+(?:\.\d+)?)'
)

# InDesign cross-references read 第<page>页“<target title>”. Carry title and
# page as [[XREF:title#page]]; resolved DITA xrefs are empty elements with
# cms:title. Page text is left to IME. Container titles map to the first
# child topic. Figure/table xrefs take the IDML ParagraphDestination caption
# (not 图 N / 表 N). href is file.dita#topic-id/title-id; never write keyref.
XREF_RE = re.compile(r'\[\[XREF:([^\[\]#]+)(?:#([^\[\]]+))?\]\]')
INDEX_RE = re.compile(r'\[\[INDEX:([^\]]+)\]\]')
IDML_GENERATED_INDEX_RE = re.compile(r'(?i)Title:Index|Title[-:]Index\b')
INDEXTERM_CHUNK_RE = re.compile(
    r"<indexterm>(?:[^<]|<indexterm>[^<]*</indexterm>)*</indexterm>"
)

XREF_ITALIC_PERIOD_RE = re.compile(
    r"(<xref\b[^>]*(?:/>|>.*?</xref>))\s*<i>\s*([。．.]+)\s*</i>",
    re.S,
)


def _unwrap_italic_punct_after_xref(text):
    """Keep the period after xref in the parent <p>, not inside <i>."""
    return XREF_ITALIC_PERIOD_RE.sub(r"\1\2", text or "")


def _indexterm_visible_text(term_xml):
    return re.sub(r"</?indexterm>", "", term_xml or "")


def _place_indexterms_in_body(xml_text):
    """Wrap the first body occurrence with <indexterm>; do not emit prolog keywords."""
    body_match = re.search(
        r"(<(?:body|conbody)\b[^>]*>)([\s\S]*?)(</(?:body|conbody)>)",
        xml_text or "",
    )
    if not body_match or "<indexterm>" not in body_match.group(2):
        return xml_text
    seen = set()

    def _keep_first(match):
        chunk = match.group(0)
        key = _indexterm_visible_text(chunk)
        if not key or key in seen:
            return ""
        seen.add(key)
        return chunk

    new_body = INDEXTERM_CHUNK_RE.sub(_keep_first, body_match.group(2))

    def _dedupe_following(match):
        chunk = match.group(1)
        following = match.group(2) or ""
        full = _indexterm_visible_text(chunk)
        leaves = re.findall(r"<indexterm>([^<]+)", chunk)
        leaf = leaves[-1] if leaves else full
        for dup in (full, leaf):
            if dup and following.startswith(dup):
                return chunk + following[len(dup):]
        return chunk + following

    new_body = re.sub(
        r"(" + INDEXTERM_CHUNK_RE.pattern + r")([^<]*)",
        _dedupe_following,
        new_body,
    )
    new_body = re.sub(
        r"<indexterm>([^<]+)</indexterm><uicontrol>\1</uicontrol>",
        r"<uicontrol><indexterm>\1</indexterm></uicontrol>",
        new_body,
    )
    return (
        xml_text[: body_match.start(2)]
        + new_body
        + xml_text[body_match.end(2) :]
    )


def _strip_xml_ns(tag):
    if isinstance(tag, str) and "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _idml_style_is_italic(style_key, font_style=""):
    if re.search(r"(?i)italic", font_style or ""):
        return True
    key = (style_key or "").strip()
    return bool(key and IDML_ITALIC_STYLE_RE.search(key))


def _idml_style_is_term(style_key):
    key = (style_key or "").strip()
    return bool(key and IDML_TERM_STYLE_RE.search(key))


def _idml_style_is_sup(style_key, position=""):
    if re.search(r"(?i)superscript", position or ""):
        return True
    key = (style_key or "").strip()
    return bool(key and IDML_SUP_STYLE_RE.search(key))


def _idml_wrap_run_text(text, ui=False, italic=False, term=False, sup=False):
    if not text:
        return text
    if ui:
        return f"{IDML_UI_MARK_OPEN}{text}{IDML_UI_MARK_CLOSE}"
    if term and text.strip():
        return f"{IDML_TERM_MARK_OPEN}{text}{IDML_TERM_MARK_CLOSE}"
    if italic and text.strip():
        return f"{IDML_I_MARK_OPEN}{text}{IDML_I_MARK_CLOSE}"
    if sup and text.strip():
        return f"[[SUP]]{text}[[/SUP]]"
    return text


def _idml_merge_adjacent_i_marks(text):
    if not text:
        return text
    text = text.replace(f"{IDML_I_MARK_CLOSE}{IDML_I_MARK_OPEN}", "")
    text = text.replace(f"{IDML_TERM_MARK_CLOSE}{IDML_TERM_MARK_OPEN}", "")
    text = text.replace(f"{IDML_UI_MARK_CLOSE}{IDML_UI_MARK_OPEN}", "")
    text = text.replace("[[/SUP]][[SUP]]", "")
    return text


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


def _idml_table_is_extra_wide(table_elem):
    widths = _idml_table_column_widths(table_elem)
    if not widths:
        return False
    return sum(widths.values()) >= IDML_EXTRA_WIDE_TABLE_PT


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


def _idml_collect_text(elem, ui_styles=None, ui=False, italic=False, term=False, sup=False):
    """Collect paragraph text from an element, skipping nested tables.

    When ``ui_styles`` is given, runs carrying an on-screen ("Silk screen")
    character style are wrapped in ``[[UI]]...[[/UI]]`` so the DITA layer can
    turn them into ``<uicontrol>``. Italic character styles become ``[[I]]``.
    Reagent-name character styles become ``[[TERM]]``.
    """
    parts = []
    for child in list(elem):
        tag = _strip_xml_ns(child.tag)
        if tag == "Table":
            continue
        if tag == "PageReference":
            marker = _idml_index_marker(child)
            if marker:
                parts.append(marker)
            continue
        if tag == "CrossReferenceSource":
            marker = _idml_xref_marker(child)
            if marker:
                parts.append(marker)
                continue
        child_style = _idml_style_key(child.get("AppliedCharacterStyle", ""))
        child_ui = ui or bool(child_style and ui_styles and child_style in ui_styles)
        child_italic = italic or _idml_style_is_italic(
            child_style, child.get("FontStyle") or ""
        )
        child_term = term or _idml_style_is_term(child_style)
        child_sup = sup or _idml_style_is_sup(
            child_style, child.get("Position") or ""
        )
        if tag == "CrossReferenceSource":
            marker = _idml_xref_marker(child)
            if marker:
                parts.append(marker)
            else:
                parts.append(_idml_collect_text(
                    child, ui_styles, child_ui, child_italic, child_term, child_sup
                ))
            continue
        if tag == "Content":
            if child.text:
                parts.append(_idml_wrap_run_text(
                    re.sub(r'[\u2028\u2029]+', ' ', child.text),
                    child_ui, child_italic, child_term, child_sup
                ))
        elif tag == "Br":
            parts.append(" ")
        else:
            parts.append(_idml_collect_text(
                child, ui_styles, child_ui, child_italic, child_term, child_sup
            ))
    return _idml_merge_adjacent_i_marks("".join(parts))


def _idml_collect_paragraph_destination_titles(story_xml):
    """Map ParagraphDestination Self ids to the destination paragraph text."""
    titles = {}
    for match in re.finditer(
        r"<ParagraphDestination\b([^>]*)/?>",
        story_xml or "",
        flags=re.S,
    ):
        self_id = re.search(r'\bSelf="([^"]+)"', match.group(1) or "")
        if not self_id:
            continue
        tail = (story_xml or "")[match.end():]
        end = tail.find("</ParagraphStyleRange>")
        window = tail[:end] if end >= 0 else tail[:800]
        title = html.unescape("".join(re.findall(r"<Content>([^<]*)</Content>", window)))
        title = title.replace("\u2008", "").replace("\u2009", " ").replace("\u200b", "")
        title = re.sub(r"[\u2028\u2029]+", " ", title)
        title = re.sub(r"[ \t]+", " ", title).strip()
        title = FIGURE_CAPTION_PREFIX_RE.sub("", title)
        title = TABLE_CAPTION_PREFIX_RE.sub("", title)
        title = title.lstrip(":：.．、- ").strip()
        if title:
            titles[html.unescape(self_id.group(1))] = title
    return titles


def _idml_collect_hyperlink_source_destinations(designmap_xml):
    """Map Hyperlink Source (CrossReferenceSource Self) to ParagraphDestination."""
    mapping = {}
    for match in re.finditer(
        r"<Hyperlink\b([^>]*)>(.*?)</Hyperlink>",
        designmap_xml or "",
        flags=re.S,
    ):
        source = re.search(r'\bSource="([^"]+)"', match.group(1) or "")
        dest = re.search(
            r'<Destination type="object">([^<]+)</Destination>',
            match.group(2) or "",
        )
        if not source or not dest:
            continue
        dest_id = html.unescape(dest.group(1).strip())
        if dest_id.startswith("ParagraphDestination"):
            mapping[source.group(1)] = dest_id
    return mapping


_IDML_XREF_DEST_TITLES = {}


def _idml_xref_marker(elem):
    """Return an ``[[XREF:title]]`` marker for a ``<CrossReferenceSource>``.

    Chinese sources read 第<page>页“<target title>”; English sources read
    ``<target title> on Page``. The page comes from the InDesign ResultText
    variable. Resolved DITA xrefs stay empty; the page is only kept so
    unresolved targets can still show a fallback.
    """
    dest_title = _IDML_XREF_DEST_TITLES.get((elem.get("Self") or "").strip())
    contents = [
        sub.text
        for sub in elem.iter()
        if _strip_xml_ns(sub.tag) == "Content" and sub.text
    ]
    text = "".join(contents)
    match = re.search(r'[\u201c"]([^\u201d"]+)[\u201d"]', text)
    title = match.group(1).strip() if match else ""
    if not title:
        en_match = re.search(r'(?i)^(.+?)\s+on\s+page\s*$', text.strip())
        if en_match:
            title = en_match.group(1).strip()
    if dest_title:
        title = dest_title
    elif not title:
        return None
    title = html.unescape(title).replace("\u200b", "")
    title = _clean_xref_title(title) or title
    page = ""
    for sub in elem.iter():
        if _strip_xml_ns(sub.tag) == "TextVariableInstance":
            result = (sub.get("ResultText") or "").strip()
            if result:
                page = result
                break
    if page and page not in {"0", "00"}:
        return f"[[XREF:{title}#{page}]]"
    return f"[[XREF:{title}]]"


def _idml_index_marker(elem):
    """Turn an InDesign ``PageReference`` into ``[[INDEX:term]]`` / nested terms."""
    ref = (elem.get("ReferencedTopic") or "").strip()
    parts = [part.strip() for part in ref.split("Topicn")[1:] if part.strip()]
    if not parts:
        return None
    return "[[INDEX:" + "/".join(parts) + "]]"


def _idml_story_is_generated_index(story_root, style_map):
    """True when the story is InDesign's generated index (letter heads + page lists)."""
    for child in story_root.iter():
        if _strip_xml_ns(child.tag) != "ParagraphStyleRange":
            continue
        key = _idml_style_key(child.get("AppliedParagraphStyle", ""))
        display = urllib.parse.unquote((style_map or {}).get(key, key) or "")
        if IDML_GENERATED_INDEX_RE.search(display):
            return True
    return False


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
    cell_fills = {}
    table_styles = {}
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
            if tag == "CellStyle":
                key = _idml_style_key(elem.get("Self") or "")
                fill = elem.get("FillColor") or ""
                if key and fill:
                    cell_fills[key] = fill
                continue
            if tag == "TableStyle":
                key = _idml_style_key(elem.get("Self") or "")
                if key:
                    table_styles[key] = {
                        "left": _idml_style_key(elem.get("LeftColumnRegionCellStyle") or ""),
                        "right": _idml_style_key(elem.get("RightColumnRegionCellStyle") or ""),
                        "body": _idml_style_key(elem.get("BodyRegionCellStyle") or ""),
                    }
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
    return style_map, list_styles, ui_styles, cell_fills, table_styles


def _load_idml_colors(zf):
    """Map Color Self ids in Graphic.xml to (Space, ColorValue)."""
    colors = {}
    for name in zf.namelist():
        if not name.replace("\\", "/").lower().endswith("graphic.xml"):
            continue
        try:
            root = ET.fromstring(zf.read(name))
        except Exception:
            continue
        for elem in root.iter():
            if _strip_xml_ns(elem.tag) != "Color":
                continue
            self_id = (elem.get("Self") or "").strip()
            values = (elem.get("ColorValue") or "").strip()
            if not self_id or not values:
                continue
            space = (elem.get("Space") or "CMYK").strip() or "CMYK"
            colors[self_id] = (space, values)
            decoded = urllib.parse.unquote(self_id)
            if decoded != self_id:
                colors[decoded] = (space, values)
    return colors


def _idml_heading_level(style_ref, style_map):
    key = _idml_style_key(style_ref)
    display = urllib.parse.unquote(style_map.get(key, key) or "")
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


def _idml_style_body_level(style_ref, style_map):
    """Nesting level encoded in body styles such as Text:L4 or Introductory sentence-L4."""
    key = _idml_style_key(style_ref)
    display = urllib.parse.unquote(style_map.get(key, key) or "")
    if IDML_HEADING_LEVEL_RE.search(display) or IDML_FRONT_TITLE_RE.search(display):
        return None
    if IDML_FIGURE_TITLE_RE.search(display) or IDML_TABLE_TITLE_RE.search(display):
        return None
    match = re.search(r"(?i)(?:^|[-:\s])L\s*(\d+)\b", display)
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


def _idml_cell_plain_for_join(text):
    return IDML_INLINE_MARK_STRIP_RE.sub("", text or "").strip()


def _idml_text_is_regulation_id(text):
    return bool(_IDML_REGULATION_ID_RE.match(_idml_cell_plain_for_join(text)))


def _idml_text_is_regulation_year(text):
    return bool(_IDML_REGULATION_YEAR_RE.match(_idml_cell_plain_for_join(text)))


def _idml_text_is_short_parenthetical(text):
    plain = _idml_cell_plain_for_join(text)
    return plain.startswith("(") and len(plain) <= 40


def _idml_split_regulation_text(text):
    """Split 'IEC 61326-1:2020 Full name' into number and title."""
    raw = (text or "").strip()
    if not raw:
        return [raw]
    match = _IDML_REGULATION_SPLIT_RE.match(_idml_cell_plain_for_join(raw))
    if not match or _idml_text_is_regulation_year(match.group(2)):
        return [raw]
    marked = _IDML_REGULATION_SPLIT_RE.match(raw)
    if marked and not _idml_text_is_regulation_year(marked.group(2)):
        return [marked.group(1).strip(), marked.group(2).strip()]
    return [match.group(1).strip(), match.group(2).strip()]


def _idml_maybe_regulation_psep(text):
    parts = _idml_split_regulation_text(text)
    if len(parts) == 2:
        return parts[0] + IDML_CELL_P_SEP + parts[1]
    return text


def _split_idml_p_parts(text):
    return [part.strip() for part in (text or "").split(IDML_CELL_P_SEP) if part.strip()]


def _idml_split_merged_uicontrol(text, rowspan=1):
    """Split a rowspan silk-screen label so IME can wrap it in a narrow column."""
    if rowspan <= 1:
        return text
    stripped = (text or "").strip()
    match = re.fullmatch(r"\[\[UI\]\](.+?)\[\[/UI\]\]", stripped)
    if not match:
        return text
    words = match.group(1).split()
    if len(words) < 2:
        return text
    return IDML_CELL_P_SEP.join(f"[[UI]]{word}[[/UI]]" for word in words)

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
            cleaned.append((_idml_maybe_regulation_psep(text), kind))
    if not cleaned:
        return ""
    kinds = {kind for _, kind in cleaned}
    if kinds <= {"ul"} or kinds <= {"ol"}:
        kind = next(iter(kinds))
        open_m = IDML_CELL_UL_OPEN if kind == "ul" else IDML_CELL_OL_OPEN
        close_m = IDML_CELL_UL_CLOSE if kind == "ul" else IDML_CELL_OL_CLOSE
        merged = []
        for text, _kind in cleaned:
            if merged and _idml_text_is_regulation_id(merged[-1].split(IDML_CELL_P_SEP)[0]):
                id_part, *rest = merged[-1].split(IDML_CELL_P_SEP)
                if _idml_text_is_regulation_year(text):
                    merged[-1] = (id_part + " " + text).strip()
                    if rest:
                        merged[-1] += IDML_CELL_P_SEP + IDML_CELL_P_SEP.join(rest)
                    continue
                if IDML_CELL_P_SEP not in merged[-1]:
                    merged[-1] = merged[-1] + IDML_CELL_P_SEP + text
                    continue
            merged.append(text)
        return open_m + IDML_CELL_LIST_SEP.join(merged) + close_m
    parts = []
    list_buf = []
    list_kind = None

    def flush_list():
        nonlocal list_kind
        if not list_buf:
            return
        open_m = IDML_CELL_UL_OPEN if list_kind == "ul" else IDML_CELL_OL_OPEN
        close_m = IDML_CELL_UL_CLOSE if list_kind == "ul" else IDML_CELL_OL_CLOSE
        parts.append(open_m + IDML_CELL_LIST_SEP.join(list_buf) + close_m)
        list_buf.clear()
        list_kind = None

    for text, kind in cleaned:
        if kind in ("ul", "ol"):
            if list_buf and list_kind != kind:
                flush_list()
            list_kind = kind
            list_buf.append(text)
            continue
        if list_buf:
            if _idml_text_is_short_parenthetical(text):
                list_buf[-1] = f"{list_buf[-1]} {text}".strip()
            elif (
                _idml_text_is_regulation_id(list_buf[-1].split(IDML_CELL_P_SEP)[0])
                and _idml_text_is_regulation_year(text)
            ):
                id_part, *rest = list_buf[-1].split(IDML_CELL_P_SEP)
                list_buf[-1] = (id_part + " " + text).strip()
                if rest:
                    list_buf[-1] += IDML_CELL_P_SEP + IDML_CELL_P_SEP.join(rest)
            else:
                list_buf[-1] = f"{list_buf[-1]}{IDML_CELL_P_SEP}{text}"
            continue
        flush_list()
        if parts and _idml_text_is_regulation_id(parts[-1].split(IDML_CELL_P_SEP)[0]):
            id_part, *rest = parts[-1].split(IDML_CELL_P_SEP)
            if _idml_text_is_regulation_year(text):
                parts[-1] = (id_part + " " + text).strip()
                if rest:
                    parts[-1] += IDML_CELL_P_SEP + IDML_CELL_P_SEP.join(rest)
                continue
        parts.append(text)
    flush_list()
    return IDML_CELL_P_SEP.join(parts)


def _idml_inline_images(text, uris, image_resolver):
    """Replace positional icon placeholders with inline image markdown."""
    def repl(match):
        index = int(match.group(1))
        replacement = ""
        if index < len(uris) and image_resolver is not None:
            path = image_resolver(uris[index])
            if path:
                replacement = _md_image_markup(path)
        if replacement:
            return replacement
        start, end = match.start(), match.end()
        left = text[start - 1] if start else ""
        right = text[end] if end < len(text) else ""
        if left.isalnum() and right.isalnum():
            return " "
        return ""

    return re.sub(r"\x00IMG(\d+)\x00", repl, text)


def _idml_nested_callout_cell_text(table_elem, ui_styles=None, image_resolver=None):
    """Flatten a table nested in a cell; callouts become [[NOTE:type]] markers."""
    lines = _idml_table_to_markdown(table_elem, ui_styles, image_resolver)
    if not lines:
        return ""
    header = (lines[0] or "").strip()
    match = re.search(r"\[\[NOTE:(\w+)\]\]", header)
    if not match:
        return _idml_collect_text(table_elem, ui_styles).strip()
    bodies = []
    for line in lines[1:]:
        body = (line or "").strip()
        if not body.startswith("|") or not body.endswith("|"):
            continue
        inner = body[1:-1].strip()
        if not inner or re.match(r"^:?-+:?$", inner.replace(" ", "").replace("|", "")):
            continue
        bodies.append(inner)
    if not bodies:
        return ""
    return f"[[NOTE:{match.group(1)}]]{_idml_note_body_marker(bodies)}[[/NOTE]]"


def _idml_note_body_marker(bodies):
    """Keep callout list items as [[UL]] so nested cell notes rebuild <ul>."""
    parts = []
    list_items = []

    def flush_list():
        if not list_items:
            return
        parts.append(
            IDML_CELL_UL_OPEN
            + IDML_CELL_LIST_SEP.join(list_items)
            + IDML_CELL_UL_CLOSE
        )
        list_items.clear()

    for body in bodies:
        if (body or "").startswith("- "):
            list_items.append(body[2:].strip())
            continue
        flush_list()
        if body:
            parts.append(body)
    flush_list()
    return "".join(parts)


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
            para, split_on_br=True, ui_styles=ui_styles
        )
        for piece_kind, value, extra in pieces:
            if piece_kind == "text":
                text = _idml_inline_images(value, extra, image_resolver).strip()
            elif piece_kind == "image":
                path = image_resolver(value) if image_resolver else None
                text = _md_image_markup(path) if path else ""
            elif piece_kind == "table":
                text = _idml_nested_callout_cell_text(value, ui_styles, image_resolver)
            else:
                text = _idml_collect_text(value, ui_styles).strip()
            if text:
                items.append((text, list_kind))
        has_linked_image = any(
            piece_kind == "image" or (piece_kind == "text" and extra)
            for piece_kind, _value, extra in pieces
        )
        if image_resolver and not has_linked_image:
            for path in _idml_export_nested_native_svgs(para, image_resolver):
                items.append((_md_image_markup(path), False))

    def visit(node):
        for child in list(node):
            tag = _strip_xml_ns(child.tag)
            if tag == "ParagraphStyleRange":
                add_paragraph(child)
                continue
            if tag == "Table":
                # A nested callout inside a cell becomes a note marker.
                text = _idml_nested_callout_cell_text(child, ui_styles, image_resolver)
                if text:
                    items.append((text, False))
                continue
            if tag in ("Image", "PDF", "EPS"):
                uri = _idml_graphic_ref(child)
                if uri and image_resolver:
                    path = image_resolver(uri)
                    if path:
                        items.append((_md_image_markup(path), False))
                continue
            if tag == "Link":
                uri = child.get("LinkResourceURI") or child.get("URI") or ""
                if uri and image_resolver:
                    path = image_resolver(uri)
                    if path:
                        items.append((_md_image_markup(path), False))
                continue
            if tag == "Rectangle":
                uri = _idml_graphic_ref(child)
                if uri and image_resolver:
                    path = image_resolver(uri)
                    if path:
                        items.append((_md_image_markup(path), False))
                        continue
            if tag in ("Group", "Rectangle", "Oval", "Polygon"):
                path = _idml_export_native_cell_svg(child, image_resolver)
                if path:
                    items.append((_md_image_markup(path), False))
                    continue
            visit(child)

    visit(cell)
    if not saw_paragraph:
        text = _idml_collect_text(cell, ui_styles).strip()
        if text:
            items.append((text, False))
    return items


def _idml_clear_white_header_corner(grid, cell_elems, header_row_count):
    """Drop leftover text in a white-cell 0:0 next to heading header cells."""
    if header_row_count < 1:
        return
    corner = cell_elems.get((0, 0))
    neighbor = cell_elems.get((0, 1))
    if corner is None or neighbor is None:
        return
    style_0 = urllib.parse.unquote(corner.get("AppliedCellStyle") or "")
    style_1 = urllib.parse.unquote(neighbor.get("AppliedCellStyle") or "")
    if not re.search(r"(?i)white\s*cell", style_0):
        return
    if not re.search(r"(?i)heading", style_1):
        return
    raw = grid.get((0, 0), "")
    grid[(0, 0)] = "".join(re.findall(r"\[\[[^\]]+\]\]", raw))


def _idml_cell_plain_markdown(text):
    return IDML_SPAN_MARK_RE.sub("", IDML_BG_MARK_RE.sub("", text or "")).strip()


TABLE_INLINE_MARK_RE = re.compile(
    r"\[\[(?:/?B|/?I|/?UI|/?TERM|FIGCAP|KEEP)\]\]"
)


def _table_cell_visible_text(text):
    if not text or text == IDML_SPAN_COVERED:
        return ""
    visible = _idml_cell_plain_markdown(text)
    visible = _strip_md_image_tokens(visible)
    visible = TABLE_INLINE_MARK_RE.sub("", visible)
    return " ".join(visible.split()).strip()


def _table_cell_rowspan(text):
    if not text or text == IDML_SPAN_COVERED:
        return 1
    match = IDML_SPAN_MARK_RE.search(text)
    if match is None:
        return 1
    try:
        return max(1, int(match.group(2)))
    except ValueError:
        return 1


_PARTS_LEGEND_HEADERS = {
    ("no", "name", "description"),
    ("序号", "名称", "说明"),
}


def _is_untitled_parts_legend_table(rows, has_title=False):
    """Untitled 3-col No./Name/Description tables are figure legends."""
    if has_title or not rows or len(rows[0]) != 3:
        return False
    headers = tuple(
        re.sub(r"[.．。]", "", _table_cell_visible_text(cell)).strip().lower()
        for cell in rows[0]
    )
    return headers in _PARTS_LEGEND_HEADERS


def _table_cell_looks_like_value(text):
    visible = _table_cell_visible_text(text)
    if not visible:
        return False
    if len(visible) > 32:
        return True
    if "@" in visible or re.search(r"https?://", visible, re.I):
        return True
    if re.search(r"\d", visible) and not re.match(r"(?i)^(no\.?|n/?a|n\.a\.?)$", visible):
        return True
    if re.search(
        r"(?i)(有限公司|公司|大学|研究所|\bltd\.?|\bllc\b|\binc\.?|\bgmbh\b|\bsia\b|\bcorp\.?)",
        visible,
    ):
        return True
    return False


def _table_grid_is_vertical_header(grid):
    """True when the first column is the header, so row 0 stays in tbody."""
    if not grid or len(grid) < 2:
        return False
    width = len(grid[0])
    if width < 2:
        return False
    first = grid[0]
    non_stub = []
    has_stub = False
    for cell in first:
        if (cell or "") == IDML_SPAN_COVERED:
            continue
        if _table_cell_rowspan(cell) > 1:
            has_stub = True
            continue
        non_stub.append(cell)
    if has_stub:
        stub_span = max(
            (_table_cell_rowspan(cell) for cell in first if (cell or "") != IDML_SPAN_COVERED),
            default=1,
        )
        if stub_span >= len(grid):
            return True
        if not non_stub:
            return True
        return any(_table_cell_looks_like_value(cell) for cell in non_stub)
    if width != 2:
        return False
    labels = [_table_cell_visible_text(row[0]) if row else "" for row in grid]
    if not all(labels) or any(len(label) > 40 for label in labels):
        return False
    return _table_cell_looks_like_value(first[1] if len(first) > 1 else "")


def _idml_cell_is_image_only(text):
    plain = _idml_cell_plain_markdown(text)
    if not plain:
        return False
    return bool(list(_iter_md_images(plain))) and not _strip_md_image_tokens(plain)


def _idml_cell_is_caption_text(text):
    plain = _idml_cell_plain_markdown(text)
    return bool(plain) and not list(_iter_md_images(plain))


def _idml_md_image_is_callout_icon(text):
    for match in _iter_md_images(text or ""):
        name = os.path.basename((match.href or "").replace("\\", "/")).lower()
        if name.startswith("icon") or re.search(
            r"(?i)warning|danger|caution|tips|note|biological|biohazard", name
        ):
            return True
    return False


def _idml_collapse_image_caption_rows(grid, width, header_row_count):
    """Turn a 2-col image + caption table into a headerless single image row."""
    row_indexes = sorted({r for r, _ in grid})
    if width != 2 or len(row_indexes) != 2:
        return header_row_count
    r0, r1 = row_indexes
    row0 = [grid.get((r0, c), "") for c in range(width)]
    row1 = [grid.get((r1, c), "") for c in range(width)]
    if not all(_idml_cell_is_image_only(cell) for cell in row0):
        return header_row_count
    if not all(_idml_cell_is_caption_text(cell) for cell in row1):
        return header_row_count
    for col in range(width):
        grid.pop((r1, col), None)
        image_cell = IDML_BG_MARK_RE.sub("", grid.get((r0, col), ""))
        caption = _idml_cell_plain_markdown(row1[col])
        if caption.startswith(IDML_FIGCAP_MARKER):
            caption = caption[len(IDML_FIGCAP_MARKER):].strip()
        if caption:
            image_cell = image_cell.rstrip() + " " + IDML_FIGCAP_MARKER + caption
        grid[(r0, col)] = image_cell
    return 0

def _idml_table_to_markdown(table_elem, ui_styles=None, image_resolver=None, cell_fills=None, table_styles=None):
    # IDML stores cells as direct children of <Table>, positioned by a
    # "<col>:<row>" Name attribute (columns are the first index, rows the
    # second; the table's ColumnCount/RowCount confirm this order).
    grid = {}
    cell_elems = {}
    max_col = -1
    try:
        header_row_count = int(table_elem.get("HeaderRowCount") or "0") or 0
    except (TypeError, ValueError):
        header_row_count = 0
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
        bg = _idml_cell_bgcolor(child, cell_fills, table_elem, table_styles, col)
        if bg and row >= header_row_count:
            text = f"[[BG:{bg}]]{text}"
        try:
            rowspan = max(1, int(child.get("RowSpan") or "1"))
            colspan = max(1, int(child.get("ColumnSpan") or "1"))
        except ValueError:
            rowspan, colspan = 1, 1
        text = _idml_split_merged_uicontrol(text, rowspan)
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
    strip_images = _strip_md_image_tokens
    _idml_clear_white_header_corner(grid, cell_elems, header_row_count)
    header_row_count = _idml_collapse_image_caption_rows(grid, width, header_row_count)
    row_indexes = sorted({r for r, _ in grid})
    # A callout box (warning/tip) is a narrow table with no header row whose
    # cells all sit in a leading icon column: the icon cell carries a symbol
    # image (or a callout style) and no text, and the note body is the text of
    # the remaining cells. Emit it as [[NOTE:type]] so the DITA layer produces
    # a <note>, with the type taken from the icon. A wider table, or one whose
    # leading column holds real content, is a normal table.
    if row_indexes and header_row_count == 0 and 1 <= width <= 2:
        lead_texts = [
            strip_images(IDML_BG_MARK_RE.sub("", strip_spans(grid.get((r, 0), "")))).strip()
            for r in row_indexes
        ]
        lead_cells = [cell_elems.get((r, 0)) for r in row_indexes]
        icon_column = all(
            (not text) or _idml_cell_is_callout(cell)
            for text, cell in zip(lead_texts, lead_cells)
        ) and not any(lead_texts)
        has_content_shot = any(
            _idml_cell_is_image_only(grid.get((r, c), ""))
            and not _idml_md_image_is_callout_icon(grid.get((r, c), ""))
            for r in row_indexes
            for c in range(width)
        )
        if icon_column and not has_content_shot:
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
        header_text = IDML_BG_MARK_RE.sub("", header_text).strip()
        # A filled 1-column cell (RUO red bar, gray heading row) is a table,
        # not a tip/warning callout.
        if (
            (not header_text or _idml_cell_is_callout(header_cell))
            and not _idml_cell_bgcolor(header_cell, cell_fills, table_elem, table_styles, 0)
        ):
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
    if header_row_count == 0 and len(row_indexes) > 1:
        if not _table_grid_is_vertical_header([render(r) for r in row_indexes]):
            header_row_count = 1
    if header_row_count > 0:
        header_rows = set(row_indexes[:header_row_count])
        for key, value in list(grid.items()):
            if key[0] in header_rows:
                grid[key] = IDML_BG_MARK_RE.sub("", value or "")
    lines = []
    relative_widths = _idml_relative_colwidths(
        _idml_table_column_widths(table_elem), width
    )
    if relative_widths:
        lines.append("[[COLW:" + ",".join(relative_widths) + "]]")
    if _idml_table_is_extra_wide(table_elem):
        lines.append("[[TWIDE:180mm]]")
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


def _idml_fill_to_hex(fill_ref, style_name=""):
    """Map IDML CMYK / warning-RUO / heading-frame fills to IME hex colors."""
    hay = f"{fill_ref or ''} {style_name or ''}"
    if re.search(r"(?i)research\s*use", hay):
        return "#FF0000"
    if re.search(r"(?i)ruo", hay) and re.search(r"(?i)warning|single\s+sentence", hay):
        return "#FF0000"
    if re.search(r"(?i)heading.*frames|frames.*heading", hay):
        return "#C0C0C0"
    match = IDML_CMYK_COLOR_RE.search(fill_ref or "")
    if not match:
        return ""
    cyan, magenta, yellow, black = (float(part) for part in match.groups())
    if magenta >= 80 and yellow >= 80 and cyan <= 20 and black <= 20:
        return "#FF0000"
    if cyan <= 10 and magenta <= 10 and yellow <= 10 and black >= 40:
        return "#C0C0C0"
    return ""


def _idml_inherited_cell_style_key(table_elem, col, table_styles):
    """Region cell style when the cell itself is $ID/[None]."""
    if table_elem is None:
        return ""
    info = (table_styles or {}).get(
        _idml_style_key(table_elem.get("AppliedTableStyle") or "")
    ) or {}
    try:
        width = int(table_elem.get("ColumnCount") or "0") or 0
    except ValueError:
        width = 0
    if col == 0 and info.get("left"):
        return info["left"]
    if width and col == width - 1 and info.get("right"):
        return info["right"]
    return info.get("body") or ""


def _idml_cell_bgcolor(cell, cell_fills=None, table_elem=None, table_styles=None, col=0):
    if cell is None:
        return ""
    fill = cell.get("FillColor") or ""
    style_ref = cell.get("AppliedCellStyle") or ""
    style_key = _idml_style_key(style_ref)
    if (not style_key) or style_key.endswith("[None]") or style_key in ("None", "[None]"):
        style_key = _idml_inherited_cell_style_key(table_elem, col, table_styles)
    style_fill = (cell_fills or {}).get(style_key) or ""
    para_styles = " ".join(_idml_cell_paragraph_styles(cell))
    return (
        _idml_fill_to_hex(fill, style_ref)
        or _idml_fill_to_hex(style_fill, style_key)
        or _idml_fill_to_hex("", para_styles)
        or _idml_fill_to_hex("", _idml_style_key((table_elem.get("AppliedTableStyle") if table_elem is not None else "") or ""))
    )


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
    if re.search(r"(?i)biological|biohazard|bio[-_\s]?risk", joined):
        return "biological_risk"
    if re.search(r"(?i)danger", joined):
        return "danger"
    uri_joined = " ".join(
        urllib.parse.unquote(uri).lower() for uri in _idml_image_links(cell)
    )
    if re.search(r"(?i)(?:^|[/\\\\_.-])tips?(?:[/\\\\_.-]|$)|label\\d+_tips", uri_joined):
        return "tip"
    if any(keyword in joined for keyword in ("warning", "warn", "risk")):
        return "warning"
    if "caution" in joined:
        return "caution"
    return "tip"


def _note_type_from_icon_href(href):
    """Note type encoded in a warning/caution/tips icon filename."""
    name = os.path.basename(urllib.parse.unquote(href or "")).replace("\\", "/").lower()
    name = os.path.basename(name)
    if re.search(r"biological|biohazard|bio[-_]?risk", name):
        return "biological_risk"
    if re.search(r"danger", name):
        return "danger"
    if re.search(r"caution", name):
        return "caution"
    if re.search(r"warning|icon_warn", name):
        return "warning"
    if re.search(r"icon_note|tips", name):
        return "tip"
    return None


def _idml_xmp_blob(elem):
    parts = []
    for node in elem.iter():
        if _strip_xml_ns(node.tag) == "Contents" and node.text:
            parts.append(node.text)
    return "\n".join(parts)


def _idml_xmp_title(elem):
    blob = _idml_xmp_blob(elem)
    match = re.search(r"<dc:title>[\s\S]*?<rdf:li[^>]*>([^<]+)</rdf:li>", blob, re.I)
    return (match.group(1).strip() if match else "") or ""


def _idml_xmp_jpeg_bytes(elem):
    blob = _idml_xmp_blob(elem)
    match = re.search(r"<xmpGImg:image>([\s\S]*?)</xmpGImg:image>", blob, re.I)
    if not match:
        return None
    raw = (
        match.group(1)
        .replace("&#xA;", "")
        .replace("&#xD;", "")
        .replace("\n", "")
        .replace("\r", "")
        .replace(" ", "")
    )
    try:
        data = base64.b64decode(raw)
    except Exception:
        return None
    if not data.startswith(b"\xff\xd8"):
        return None
    return data


def _idml_embedded_pdf_bytes(elem):
    """Decode a PDF element's Contents when it stores an embedded PDF."""
    for node in elem.iter():
        if _strip_xml_ns(node.tag) != "Contents" or not (node.text or "").strip():
            continue
        raw = re.sub(r"\s+", "", node.text)
        if not raw.startswith("JVBERi"):
            continue
        try:
            data = base64.b64decode(raw)
        except Exception:
            continue
        if data.startswith(b"%PDF"):
            return data
    return None


def _idml_rasterize_pdf_jpeg(pdf_bytes):
    """Rasterize the first page of an embedded PDF to JPEG bytes."""
    if not pdf_bytes:
        return None
    try:
        import fitz
    except ImportError:
        return None
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            if doc.page_count < 1:
                return None
            pix = doc[0].get_pixmap(matrix=fitz.Matrix(3, 3), alpha=False)
            return pix.tobytes("jpeg")
        finally:
            doc.close()
    except Exception:
        return None


def _idml_first_link_uri(elem):
    for node in elem.iter():
        if _strip_xml_ns(node.tag) != "Link":
            continue
        uri = node.get("LinkResourceURI") or node.get("URI") or ""
        if uri:
            return uri
    return ""


def _idml_graphic_ref(elem):
    uri = _idml_first_link_uri(elem)
    if uri:
        return uri
    title = _idml_xmp_title(elem)
    if title:
        return f"xmp:{title}"
    for node in elem.iter():
        tag = _strip_xml_ns(node.tag)
        if tag in ("PDF", "Image", "EPS") and node is not elem:
            nested_id = (node.get("Self") or "").strip()
            if nested_id:
                return f"xmp:{nested_id}"
    self_id = (elem.get("Self") or "").strip()
    return f"xmp:{self_id}" if self_id else ""


def _idml_thumb_lookup_keys(link_uri):
    raw = urllib.parse.unquote(link_uri or "").replace("\\", "/")
    if raw.lower().startswith("file:"):
        raw = raw[5:]
    keys = []
    if raw.lower().startswith("xmp:"):
        title = raw[4:].strip()
        stem = os.path.splitext(title)[0]
        keys.extend([title.lower(), stem.lower(), f"xmp:{title.lower()}", f"xmp:{stem.lower()}"])
        return [k for k in keys if k]
    base = os.path.basename(raw).strip()
    stem, _ext = os.path.splitext(base)
    keys.extend([stem.lower(), base.lower(), f"xmp:{stem.lower()}"])
    alt = re.sub(r"[ _]+\d+$", "", stem).strip()
    if alt and alt.lower() != stem.lower():
        keys.append(alt.lower())
        keys.append(f"xmp:{alt.lower()}")
    return [k for k in keys if k]


def _idml_collect_xmp_thumbnails(zf, namelist):
    """Map link stems / XMP titles to JPEG preview bytes embedded in IDML."""
    thumbs = {}
    for name in namelist:
        if name.endswith("/") or not name.lower().endswith(".xml"):
            continue
        low = name.lower().replace("\\", "/")
        if "/stories/" not in f"/{low}" and not low.startswith("stories/"):
            continue
        try:
            root = ET.fromstring(zf.read(name))
        except Exception:
            continue
        for node in root.iter():
            tag = _strip_xml_ns(node.tag)
            if tag not in ("PDF", "Image", "EPS"):
                continue
            jpeg = _idml_xmp_jpeg_bytes(node)
            if not jpeg:
                pdf_bytes = _idml_embedded_pdf_bytes(node)
                if pdf_bytes:
                    jpeg = _idml_rasterize_pdf_jpeg(pdf_bytes)
            if not jpeg:
                continue
            keys = []
            uri = _idml_first_link_uri(node)
            if uri:
                keys.extend(_idml_thumb_lookup_keys(uri))
            title = _idml_xmp_title(node)
            if title:
                keys.extend(_idml_thumb_lookup_keys(f"xmp:{title}"))
            self_id = (node.get("Self") or "").strip()
            if self_id:
                keys.append(f"xmp:{self_id.lower()}")
            for key in keys:
                thumbs.setdefault(key, jpeg)
    return thumbs


def _idml_resolve_xmp_thumb(link_uri, thumbs, media_dir, cache):
    if link_uri in cache:
        return cache[link_uri]
    blob = None
    for key in _idml_thumb_lookup_keys(link_uri):
        blob = thumbs.get(key)
        if blob:
            break
    if not blob:
        cache[link_uri] = None
        return None
    raw = urllib.parse.unquote(link_uri or "")
    if raw.lower().startswith("xmp:"):
        stem = raw[4:]
    else:
        stem = os.path.splitext(os.path.basename(raw.replace("\\", "/")))[0]
    safe_stem = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", stem).strip() or "image"
    out_path = os.path.join(media_dir, f"{safe_stem}.jpg")
    counter = 1
    while os.path.exists(out_path):
        out_path = os.path.join(media_dir, f"{safe_stem}_{counter}.jpg")
        counter += 1
    try:
        with open(out_path, "wb") as handle:
            handle.write(blob)
    except Exception:
        cache[link_uri] = None
        return None
    cache[link_uri] = out_path
    return out_path


def _idml_image_links(elem):
    links = []
    for child in list(elem):
        tag = _strip_xml_ns(child.tag)
        if tag == "Table":
            # Images anchored in a callout table belong to that table, not to
            # the surrounding paragraph.
            continue
        if tag in ("PDF", "Image", "EPS", "SVG"):
            uri = _idml_graphic_ref(child)
            if uri:
                links.append(uri)
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
            for replacement in _idml_deferred_replacements(ext.lower()):
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
        text = re.sub(r'[ \t\u00a0\u2028\u2029]+', ' ', "".join(buffer)).strip()
        text = _idml_merge_adjacent_i_marks(text)
        if text:
            pieces.append(("text", text, list(images)))
        else:
            for uri in images:
                pieces.append(("image", uri, None))
        buffer.clear()
        images.clear()

    def visit(node, ui=False, italic=False, term=False, sup=False):
        for sub in list(node):
            sub_tag = _strip_xml_ns(sub.tag)
            sub_style = _idml_style_key(sub.get("AppliedCharacterStyle", ""))
            sub_ui = ui or bool(sub_style and ui_styles and sub_style in ui_styles)
            sub_italic = italic or _idml_style_is_italic(
                sub_style, sub.get("FontStyle") or ""
            )
            sub_term = term or _idml_style_is_term(sub_style)
            sub_sup = sup or _idml_style_is_sup(
                sub_style, sub.get("Position") or ""
            )
            if sub_tag == "Content":
                if sub.text:
                    buffer.append(_idml_wrap_run_text(
                        sub.text, sub_ui, sub_italic, sub_term, sub_sup
                    ))
            elif sub_tag == "Br":
                if split_on_br:
                    flush()
                else:
                    buffer.append(" ")
            elif sub_tag == "Table":
                flush()
                pieces.append(("table", sub, None))
            elif sub_tag in ("PDF", "Image", "EPS", "SVG"):
                uri = _idml_graphic_ref(sub)
                if uri:
                    placeholder = f"\x00IMG{len(images)}\x00"
                    images.append(uri)
                    buffer.append(placeholder)
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
                    visit(sub, sub_ui, sub_italic, sub_term, sub_sup)
            elif sub_tag == "PageReference":
                marker = _idml_index_marker(sub)
                if marker:
                    buffer.append(marker)
            else:
                visit(sub, sub_ui, sub_italic, sub_term, sub_sup)

    visit(para)
    flush()
    return pieces


def _idml_is_inline_icon(uri):
    base = urllib.parse.unquote(os.path.basename((uri or "").replace("\\", "/")))
    low = base.lower()
    if low.startswith("xmp:"):
        low = low[4:]
    return low.startswith("icon") or low.startswith("formula_") or low.startswith("button_")


def _idml_paragraph_has_only_inline_icons(elem):
    uris = _idml_image_links(elem)
    return bool(uris) and all(_idml_is_inline_icon(uri) for uri in uris)


def _idml_walk(elem, style_map, list_styles, blocks, image_resolver=None, ui_styles=None, cell_fills=None, table_styles=None):
    def emit_piece(piece_kind, value):
        if piece_kind == "table":
            table_lines = _idml_table_to_markdown(
                value, ui_styles, image_resolver, cell_fills, table_styles
            )
            if table_lines:
                blocks.append({"kind": "table", "lines": table_lines})
        elif piece_kind == "image":
            blocks.append({"kind": "image", "uri": value})

    for child in list(elem):
        tag = _strip_xml_ns(child.tag)
        if tag == "Table":
            table_lines = _idml_table_to_markdown(
                child, ui_styles, image_resolver, cell_fills, table_styles
            )
            if table_lines:
                blocks.append({"kind": "table", "lines": table_lines})
            continue
        if tag == "ParagraphStyleRange":
            text = re.sub(r'[ \t\u00a0\u2028\u2029]+', ' ', _idml_collect_text(child)).strip()
            style_ref = child.get("AppliedParagraphStyle", "")
            style_key = _idml_style_key(style_ref)
            display = urllib.parse.unquote(
                (style_key and style_map.get(style_key, "")) or style_key or ""
            )
            if IDML_GENERATED_INDEX_RE.search(display):
                continue
            keep_prefix = IDML_KEEP_MARKER if IDML_KEEP_STYLE_RE.search(display) else ""
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
                                    "text": _idml_maybe_regulation_psep(
                                        _idml_inline_images(value, extra, image_resolver) if extra else value
                                    ),
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
                        body_level = _idml_style_body_level(style_ref, style_map)
                        for piece_kind, value, extra in _idml_paragraph_pieces(
                            child, split_on_br=True, ui_styles=ui_styles
                        ):
                            if piece_kind == "text":
                                body_text = _idml_inline_images(value, extra, image_resolver) if extra else value
                                blocks.append({
                                    "kind": "para",
                                    "level": 0,
                                    "text": f"{keep_prefix}{_idml_maybe_regulation_psep(body_text)}" if keep_prefix else _idml_maybe_regulation_psep(body_text),
                                    "marker": None,
                                    "list_level": body_level,
                                    "appendix": False,
                                })
                            else:
                                emit_piece(piece_kind, value)
                        continue
                    if marker == IDML_TABCAP_MARKER and re.search(r'(?i)wide', display):
                        blocks.append({
                            "kind": "para",
                            "level": 0,
                            "text": "[[TWIDE:180mm]]",
                            "marker": None,
                            "appendix": False,
                        })
                    if level:
                        heading_parts = []
                        for piece_kind, value, _extra in _idml_paragraph_pieces(
                            child, split_on_br=True, ui_styles=ui_styles
                        ):
                            if piece_kind != "text":
                                continue
                            piece_text = re.sub(r'[ \t\u00a0\u2028\u2029]+', ' ', value or "").strip()
                            if piece_text:
                                heading_parts.append(piece_text)
                        if not heading_parts:
                            heading_parts = [text]
                        first_heading = True
                        for piece_text in heading_parts:
                            as_heading = first_heading
                            if not as_heading:
                                compact = piece_text.strip()
                                as_heading = bool(
                                    compact
                                    and len(compact) <= 80
                                    and not re.search(r'[.!?;，。；]$', compact)
                                    and not compact.endswith(("：", ":"))
                                )
                            first_heading = False
                            blocks.append({
                                "kind": "heading" if as_heading else "para",
                                "level": level if as_heading else 0,
                                "text": piece_text,
                                "marker": None,
                                "appendix": bool(as_heading) and bool(
                                    IDML_APPENDIX_STYLE_RE.search(display)
                                ),
                            })
                    else:
                        blocks.append({
                            "kind": "para",
                            "level": 0,
                            "text": keep_prefix + re.sub(
                                r'[ \t\u00a0\u2028\u2029]+', ' ',
                                _idml_collect_text(child, ui_styles),
                            ).strip(),
                            "marker": marker,
                            "appendix": False,
                        })
            for uri in _idml_image_links(child):
                blocks.append({"kind": "image", "uri": uri})
            # A callout table can be anchored inside a paragraph; recurse so the
            # nested table is emitted after the paragraph's own text.
            if any(_strip_xml_ns(d.tag) == "Table" for d in child.iter()):
                _idml_walk(child, style_map, list_styles, blocks, image_resolver, ui_styles, cell_fills, table_styles)
            continue
        _idml_walk(child, style_map, list_styles, blocks, image_resolver, ui_styles, cell_fills, table_styles)


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
    want_stem = _idml_normalize_image_stem(os.path.splitext(base_name)[0]).lower()
    want_ext = os.path.splitext(base_name)[1].lower()
    if not want_stem:
        return None
    fuzzy = []
    for name in namelist:
        if name.endswith("/"):
            continue
        base = name.split("/")[-1]
        stem, ext = os.path.splitext(base)
        if ext.lower() != want_ext:
            continue
        if _idml_normalize_image_stem(stem).lower() == want_stem:
            fuzzy.append(name)
    for name in fuzzy:
        if name.split("/")[0].lower() == "links":
            return name
    return fuzzy[0] if fuzzy else None


def _idml_pt_to_mm(pt):
    return abs(float(pt)) * 25.4 / 72.0


def _idml_transform_scale(elem):
    transform = (elem.get("ItemTransform") if elem is not None else "") or ""
    try:
        values = [float(part) for part in transform.split()]
    except (TypeError, ValueError):
        values = []
    if len(values) == 6:
        return abs(values[0]) or 1.0, abs(values[3]) or 1.0
    return 1.0, 1.0


def _idml_frame_size_mm(elem):
    """Placed graphic size in millimetres from PathPointArray or bounds."""
    if elem is None:
        return None
    scale_x, scale_y = _idml_transform_scale(elem)
    anchors = []
    for node in elem.iter():
        if _strip_xml_ns(node.tag) != "PathPointType":
            continue
        try:
            x_val, y_val = [float(part) for part in (node.get("Anchor") or "").split()]
        except ValueError:
            continue
        anchors.append((x_val, y_val))
    if len(anchors) >= 2:
        xs = [point[0] for point in anchors]
        ys = [point[1] for point in anchors]
        width_pt = (max(xs) - min(xs)) * scale_x
        height_pt = (max(ys) - min(ys)) * scale_y
        if width_pt > 0.5 and height_pt > 0.5:
            return _idml_pt_to_mm(width_pt), _idml_pt_to_mm(height_pt)
    for node in elem.iter():
        tag = _strip_xml_ns(node.tag)
        if tag not in ("GraphicBounds", "VisibleBounds", "GeometricBounds"):
            continue
        try:
            if node.get("Top") is not None:
                width_pt = abs(float(node.get("Right")) - float(node.get("Left"))) * scale_x
                height_pt = abs(float(node.get("Bottom")) - float(node.get("Top"))) * scale_y
                if width_pt > 0.5 and height_pt > 0.5:
                    return _idml_pt_to_mm(width_pt), _idml_pt_to_mm(height_pt)
        except (TypeError, ValueError):
            pass
        text = (node.text or "").strip()
        if not text:
            continue
        try:
            parts = [float(part) for part in text.replace(",", " ").split()]
        except ValueError:
            continue
        if len(parts) == 4:
            width_pt = abs(parts[3] - parts[1]) * scale_x
            height_pt = abs(parts[2] - parts[0]) * scale_y
            if width_pt > 0.5 and height_pt > 0.5:
                return _idml_pt_to_mm(width_pt), _idml_pt_to_mm(height_pt)
    return None


def _idml_collect_placed_image_sizes(zf, namelist):
    """Map image stems to placed (width_mm, height_mm) from IDML frames."""
    sizes = {}
    for name in namelist:
        if name.endswith("/") or not name.lower().endswith(".xml"):
            continue
        try:
            root = ET.fromstring(zf.read(name))
        except Exception:
            continue
        for node in root.iter():
            if _strip_xml_ns(node.tag) not in ("Rectangle", "Oval", "Polygon"):
                continue
            size = _idml_frame_size_mm(node)
            if not size:
                continue
            for uri in _idml_image_links(node):
                raw = urllib.parse.unquote(uri or "").replace("\\", "/")
                if raw.lower().startswith("file:"):
                    raw = raw[5:]
                base = os.path.basename(raw.split(":")[-1]).strip()
                stem = os.path.splitext(base)[0].strip()
                if stem:
                    sizes[stem.lower()] = [round(size[0], 1), round(size[1], 1)]
    return sizes


def _idml_flatten_svg_embedded_raster(svg_path):
    """Extract a screenshot PNG/JPEG wrapped in an SVG so IME can display it."""
    if not svg_path or not str(svg_path).lower().endswith(".svg"):
        return None
    if not os.path.isfile(svg_path):
        return None
    try:
        text = open(svg_path, encoding="utf-8", errors="replace").read()
    except Exception:
        return None
    matches = list(re.finditer(
        r"""(?:xlink:)?href=["']data:image/(png|jpeg|jpg);base64,([A-Za-z0-9+/=\s]+)["']""",
        text,
        re.I,
    ))
    if len(matches) != 1:
        return None
    if re.search(r"<(?:text|tspan)\b", text, re.I):
        return None
    if len(re.findall(r"<(?:path|polygon|polyline|circle|ellipse)\b", text, re.I)) > 2:
        return None
    kind = matches[0].group(1).lower()
    ext = ".jpg" if kind in ("jpeg", "jpg") else ".png"
    out_path = os.path.splitext(svg_path)[0] + ext
    if os.path.isfile(out_path):
        return out_path
    try:
        data = base64.b64decode(re.sub(r"\s+", "", matches[0].group(2)))
    except Exception:
        return None
    if not data:
        return None
    try:
        with open(out_path, "wb") as handle:
            handle.write(data)
    except Exception:
        return None
    return out_path


def _idml_item_matrix(elem):
    transform = (elem.get("ItemTransform") if elem is not None else "") or ""
    try:
        values = [float(part) for part in transform.split()]
    except (TypeError, ValueError):
        values = []
    if len(values) == 6:
        return tuple(values)
    return (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def _idml_mul_matrix(left, right):
    a1, b1, c1, d1, tx1, ty1 = left
    a2, b2, c2, d2, tx2, ty2 = right
    return (
        a1 * a2 + c1 * b2,
        b1 * a2 + d1 * b2,
        a1 * c2 + c1 * d2,
        b1 * c2 + d1 * d2,
        a1 * tx2 + c1 * ty2 + tx1,
        b1 * tx2 + d1 * ty2 + ty1,
    )


def _idml_apply_matrix(matrix, x_val, y_val):
    a, b, c, d, tx, ty = matrix
    return a * x_val + c * y_val + tx, b * x_val + d * y_val + ty


def _idml_color_value_to_hex(space, values):
    try:
        parts = [float(part) for part in (values or "").split()]
    except ValueError:
        return None
    space_u = (space or "").upper()
    if space_u == "RGB" and len(parts) >= 3:
        if max(parts[:3]) <= 1.0:
            parts = [part * 255.0 for part in parts[:3]]
        red, green, blue = (max(0, min(255, int(round(part)))) for part in parts[:3])
        return f"#{red:02X}{green:02X}{blue:02X}"
    if space_u == "CMYK" and len(parts) >= 4:
        cyan, magenta, yellow, black = (part / 100.0 for part in parts[:4])
        red = round(255 * (1.0 - cyan) * (1.0 - black))
        green = round(255 * (1.0 - magenta) * (1.0 - black))
        blue = round(255 * (1.0 - yellow) * (1.0 - black))
        return f"#{red:02X}{green:02X}{blue:02X}"
    return None


def _idml_paint_hex(fill_ref, color_map=None):
    hay = (fill_ref or "").strip()
    low = hay.lower()
    if "nocolor" in low or low.endswith("/none") or "[none]" in low:
        return None
    if color_map:
        for key in (hay, urllib.parse.unquote(hay)):
            packed = color_map.get(key)
            if packed:
                hex_val = _idml_color_value_to_hex(*packed)
                if hex_val:
                    return hex_val
    if re.search(r"(?i)paper|white", hay):
        return "#FFFFFF"
    if re.search(r"(?i)black", hay):
        return "#000000"
    match = IDML_CMYK_COLOR_RE.search(hay)
    if not match:
        swatch = hay.rsplit("/", 1)[-1].strip()
        match = re.fullmatch(
            r"(?i)c(\d+(?:\.\d+)?)m(\d+(?:\.\d+)?)y(\d+(?:\.\d+)?)k(\d+(?:\.\d+)?)",
            swatch,
        )
    if not match:
        return None
    cyan, magenta, yellow, black = (float(part) / 100.0 for part in match.groups())
    red = round(255 * (1.0 - cyan) * (1.0 - black))
    green = round(255 * (1.0 - magenta) * (1.0 - black))
    blue = round(255 * (1.0 - yellow) * (1.0 - black))
    return f"#{red:02X}{green:02X}{blue:02X}"


def _idml_shape_has_placed_graphic(elem):
    for node in elem.iter():
        tag = _strip_xml_ns(node.tag)
        if tag == "Link" and (node.get("LinkResourceURI") or node.get("URI")):
            return True
        if tag in ("Image", "PDF", "EPS"):
            return True
    return False


def _idml_shape_is_native_vector(elem):
    if elem is None or _idml_shape_has_placed_graphic(elem):
        return False
    for node in elem.iter():
        tag = _strip_xml_ns(node.tag)
        if tag in ("PathPointType", "EPSText"):
            return True
    return False


def _idml_parse_xy(value):
    try:
        x_val, y_val = [float(part) for part in (value or "").split()]
    except ValueError:
        return None
    return x_val, y_val


def _idml_collect_native_paths(
    elem, parent_matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0), color_map=None
):
    paths = []
    tag = _strip_xml_ns(elem.tag)
    matrix = _idml_mul_matrix(parent_matrix, _idml_item_matrix(elem))
    if tag in ("Rectangle", "Oval", "Polygon"):
        fill = _idml_paint_hex(elem.get("FillColor") or "", color_map)
        stroke = _idml_paint_hex(elem.get("StrokeColor") or "", color_map)
        try:
            weight = float(elem.get("StrokeWeight") or "0")
        except (TypeError, ValueError):
            weight = 0.0
        for geo in elem.iter():
            if _strip_xml_ns(geo.tag) != "GeometryPathType":
                continue
            path_open = (geo.get("PathOpen") or "").lower() == "true"
            points = []
            for node in geo.iter():
                if _strip_xml_ns(node.tag) != "PathPointType":
                    continue
                anchor = _idml_parse_xy(node.get("Anchor"))
                if not anchor:
                    continue
                left = _idml_parse_xy(node.get("LeftDirection")) or anchor
                right = _idml_parse_xy(node.get("RightDirection")) or anchor
                points.append((
                    _idml_apply_matrix(matrix, *anchor),
                    _idml_apply_matrix(matrix, *left),
                    _idml_apply_matrix(matrix, *right),
                ))
            if len(points) >= 2:
                paths.append((points, fill, stroke, weight, path_open))
        if not paths:
            points = []
            for node in elem.iter():
                if _strip_xml_ns(node.tag) != "PathPointType":
                    continue
                anchor = _idml_parse_xy(node.get("Anchor"))
                if not anchor:
                    continue
                left = _idml_parse_xy(node.get("LeftDirection")) or anchor
                right = _idml_parse_xy(node.get("RightDirection")) or anchor
                points.append((
                    _idml_apply_matrix(matrix, *anchor),
                    _idml_apply_matrix(matrix, *left),
                    _idml_apply_matrix(matrix, *right),
                ))
            if len(points) >= 2:
                paths.append((points, fill, stroke, weight, False))
        return paths
    if tag == "EPSText":
        fill = _idml_paint_hex(elem.get("FillColor") or "", color_map)
        stroke = _idml_paint_hex(elem.get("StrokeColor") or "", color_map)
        try:
            weight = float(elem.get("StrokeWeight") or "0")
        except (TypeError, ValueError):
            weight = 0.0
        for node in elem.iter():
            if _strip_xml_ns(node.tag) != "PathBoundingBox":
                continue
            try:
                left = float(node.get("Left"))
                top = float(node.get("Top"))
                right = float(node.get("Right"))
                bottom = float(node.get("Bottom"))
            except (TypeError, ValueError):
                break
            # PathBoundingBox is already in the same page space as PathPoint
            # anchors; skip this element's ItemTransform.
            points = []
            for x_val, y_val in (
                (left, top),
                (right, top),
                (right, bottom),
                (left, bottom),
            ):
                anchor = _idml_apply_matrix(parent_matrix, x_val, y_val)
                points.append((anchor, anchor, anchor))
            if len(points) >= 2:
                paths.append((points, fill, stroke, weight, False))
            break
        return paths
    for child in list(elem):
        child_tag = _strip_xml_ns(child.tag)
        if child_tag in ("Group", "Rectangle", "Oval", "Polygon", "EPSText"):
            paths.extend(_idml_collect_native_paths(child, matrix, color_map))
    return paths


def _idml_svg_path_d(points, path_open, min_x, min_y):
    def fmt(pt):
        return f"{pt[0] - min_x:.3f} {pt[1] - min_y:.3f}"

    if len(points) < 2:
        return ""
    d_parts = [f"M{fmt(points[0][0])}"]
    count = len(points) if not path_open else len(points) - 1
    for index in range(count):
        curr = points[index]
        nxt = points[(index + 1) % len(points)]
        anchor0, _left0, right0 = curr
        anchor1, left1, _right1 = nxt
        if right0 == anchor0 and left1 == anchor1:
            d_parts.append(f"L{fmt(anchor1)}")
        else:
            d_parts.append(f"C{fmt(right0)} {fmt(left1)} {fmt(anchor1)}")
    if not path_open:
        d_parts.append("Z")
    return " ".join(d_parts)


def _idml_export_native_cell_svg(elem, image_resolver):
    """Write an InDesign-native shape group to SVG and return the media path."""
    if not _idml_shape_is_native_vector(elem):
        return None
    media_dir = getattr(image_resolver, "media_dir", None) if image_resolver else None
    if not media_dir:
        return None
    cache = getattr(image_resolver, "native_cache", None)
    self_id = (elem.get("Self") or "").strip()
    if cache is not None and self_id in cache:
        return cache[self_id]
    color_map = getattr(image_resolver, "color_map", None) if image_resolver else None
    paths = _idml_collect_native_paths(elem, color_map=color_map)
    if not paths:
        return None
    xs = [
        coord[0]
        for points, _fill, _stroke, _weight, _open in paths
        for point in points
        for coord in point
    ]
    ys = [
        coord[1]
        for points, _fill, _stroke, _weight, _open in paths
        for point in points
        for coord in point
    ]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    width = max(max_x - min_x, 0.5)
    height = max(max_y - min_y, 0.5)
    pad = max(width, height) * 0.04
    min_x -= pad
    min_y -= pad
    width += pad * 2
    height += pad * 2
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.3f} {height:.3f}" '
            f'width="{_idml_pt_to_mm(width):.2f}mm" height="{_idml_pt_to_mm(height):.2f}mm">'
        ),
    ]
    for points, fill, stroke, weight, path_open in paths:
        d_attr = _idml_svg_path_d(points, path_open, min_x, min_y)
        if not d_attr:
            continue
        fill_attr = f'fill="{fill}"' if fill else 'fill="none"'
        stroke_attr = ""
        if stroke:
            stroke_attr = f' stroke="{stroke}" stroke-width="{max(weight, 0.25):.3f}"'
        parts.append(f'<path d="{d_attr}" {fill_attr}{stroke_attr}/>')
    parts.append("</svg>")
    _ensure_dir(media_dir)
    safe_stem = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", self_id or "native_icon").strip() or "native_icon"
    out_path = os.path.join(media_dir, f"{safe_stem}.svg")
    counter = 1
    while os.path.exists(out_path):
        out_path = os.path.join(media_dir, f"{safe_stem}_{counter}.svg")
        counter += 1
    try:
        with open(out_path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(parts))
    except Exception:
        return None
    if cache is not None and self_id:
        cache[self_id] = out_path
    return out_path


def _idml_export_nested_native_svgs(elem, image_resolver):
    """Export outermost native shape groups under *elem* (e.g. cell paragraphs)."""
    exported = []

    def walk(node):
        for child in list(node):
            tag = _strip_xml_ns(child.tag)
            if tag in ("Group", "Rectangle", "Oval", "Polygon"):
                path = _idml_export_native_cell_svg(child, image_resolver)
                if path:
                    exported.append(path)
                    continue
            walk(child)

    walk(elem)
    return exported


def _idml_crop_tall_flow_svg(svg_path):
    """Crop a flow_* SVG whose viewBox is much taller than the drawn content."""
    name = os.path.basename(svg_path or "").lower()
    if not name.startswith("flow_") or not name.endswith(".svg"):
        return svg_path
    if not os.path.isfile(svg_path):
        return svg_path
    try:
        text = open(svg_path, encoding="utf-8", errors="replace").read()
    except Exception:
        return svg_path
    vb = re.search(r'viewBox="([\d.+-]+)\s+([\d.+-]+)\s+([\d.]+)\s+([\d.]+)"', text)
    if not vb:
        return svg_path
    vx, vy, vw, vh = (float(part) for part in vb.groups())
    if vw <= 0 or vh <= 0:
        return svg_path
    max_y = vy
    for tag in re.finditer(r"<(?:image|rect|text|tspan|use)\b[^>]*>", text, re.I):
        chunk = tag.group(0)
        y_match = re.search(r'\by="([\d.+-]+)"', chunk)
        h_match = re.search(r'\bheight="([\d.]+)"', chunk)
        y_val = float(y_match.group(1)) if y_match else 0.0
        h_val = float(h_match.group(1)) if h_match else 0.0
        if h_val <= 0 and re.search(r"<text\b", chunk, re.I):
            fs_match = re.search(r'font-size="([\d.]+)"', chunk)
            h_val = float(fs_match.group(1)) if fs_match else 16.0
        max_y = max(max_y, y_val + h_val)
    if max_y <= vy + 1 or max_y >= vy + vh * 0.85:
        return svg_path
    new_h = max_y - vy + 8.0
    text = re.sub(
        r'viewBox="[^"]+"',
        f'viewBox="{vx:g} {vy:g} {vw:g} {new_h:g}"',
        text,
        count=1,
    )
    text = re.sub(
        r'(<svg\b[^>]*\bheight=")[^"]+',
        lambda match: match.group(1) + f"{new_h:g}",
        text,
        count=1,
        flags=re.I,
    )
    try:
        with open(svg_path, "w", encoding="utf-8") as handle:
            handle.write(text)
    except Exception:
        return svg_path
    return svg_path


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
    target = None
    resolved_name = None
    for candidate in _idml_image_candidate_names(base_name):
        found = _idml_find_link_target(namelist, candidate)
        if found:
            target = found
            resolved_name = os.path.basename(found)
            break
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
    raster = _idml_flatten_svg_embedded_raster(out_path)
    if raster:
        out_path = raster
    else:
        _idml_crop_tall_flow_svg(out_path)
    cache[link_uri] = out_path
    return out_path


def _idml_insert_precautions_heading(markdown_text):
    """Move chapter-opening danger/warning notes under a 注意事项 / Precautions topic."""
    lines = (markdown_text or "").split("\n")
    heading_re = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
    note_re = re.compile(r"\[\[NOTE:(danger|warning)\]\]", re.I)
    precautions_re = re.compile(r"(?i)^(注意事项|precautions)$")
    out = []
    i = 0
    while i < len(lines):
        match = heading_re.match(lines[i])
        if not match or len(match.group(1)) != 1:
            out.append(lines[i])
            i += 1
            continue
        out.append(lines[i])
        title = match.group(2).strip()
        i += 1
        chunk = []
        while i < len(lines) and not heading_re.match(lines[i]):
            chunk.append(lines[i])
            i += 1
        next_title = ""
        if i < len(lines):
            next_match = heading_re.match(lines[i])
            if next_match:
                next_title = next_match.group(2).strip()
        chunk_text = "\n".join(chunk)
        if note_re.search(chunk_text) and not precautions_re.match(next_title):
            child = "注意事项" if re.search(r"[\u4e00-\u9fff]", title) else "Precautions"
            inserted = False
            rewritten = []
            for line in chunk:
                if (not inserted) and note_re.search(line):
                    if rewritten and rewritten[-1].strip():
                        rewritten.append("")
                    rewritten.append(f"## {child}")
                    rewritten.append("")
                    inserted = True
                rewritten.append(line)
            chunk = rewritten
        out.extend(chunk)
    return "\n".join(out)


def _idml_to_markdown(idml_path):
    """Convert an IDML package to intermediate markdown (docx-compatible)."""
    global _IDML_XREF_DEST_TITLES
    media_dir = os.path.splitext(idml_path)[0] + "_idml_media"
    _ensure_dir(media_dir)
    with zipfile.ZipFile(idml_path, "r") as zf:
        namelist = zf.namelist()
        style_map, list_styles, ui_styles, cell_fills, table_styles = _load_idml_styles(zf)
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
        xmp_thumbs = _idml_collect_xmp_thumbnails(zf, namelist)
        placed_sizes = _idml_collect_placed_image_sizes(zf, namelist)

        dest_titles = {}
        for name in namelist:
            low = name.lower()
            if low.startswith("stories/") and low.endswith(".xml"):
                try:
                    dest_titles.update(
                        _idml_collect_paragraph_destination_titles(
                            zf.read(name).decode("utf-8", errors="replace")
                        )
                    )
                except Exception:
                    continue
        try:
            designmap_xml = zf.read("designmap.xml").decode("utf-8", errors="replace")
        except Exception:
            designmap_xml = ""
        source_to_dest = _idml_collect_hyperlink_source_destinations(designmap_xml)
        resolved_xrefs = {}
        for src, dest in source_to_dest.items():
            title = dest_titles.get(dest) or dest_titles.get(html.unescape(dest))
            if title:
                resolved_xrefs[src] = title
        _IDML_XREF_DEST_TITLES = resolved_xrefs

        def resolve_image(link_uri):
            path = _extract_idml_image(zf, namelist, link_uri, media_dir, image_cache)
            if path:
                return path
            if image_cache.get(link_uri) is None:
                image_cache.pop(link_uri, None)
            return _idml_resolve_xmp_thumb(link_uri, xmp_thumbs, media_dir, image_cache)

        resolve_image.media_dir = media_dir
        resolve_image.native_cache = {}
        resolve_image.color_map = _load_idml_colors(zf)

        def emit_image(link_uri):
            path = resolve_image(link_uri)
            if not path:
                return
            # Images on the opening page form the cover; later images are inline.
            if content_started:
                lines.append(_md_image_markup(path))
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
            _idml_walk(story_root, style_map, list_styles, blocks, resolve_image, ui_styles, cell_fills, table_styles)
            if _idml_story_is_generated_index(story_root, style_map):
                blocks = [
                    block for block in blocks
                    if block.get("kind") == "heading"
                    and re.search(r"(?i)^(?:索引|index)$", (block.get("text") or "").strip())
                ]
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
                cover_lines.append(_md_image_markup(path))
                cover_lines.append("")
            lines = cover_lines + lines

        sidecar = os.path.join(media_dir, "_image_placed_mm.json")
        try:
            with open(sidecar, "w", encoding="utf-8") as handle:
                json.dump(placed_sizes, handle)
        except Exception:
            pass

    _IDML_XREF_DEST_TITLES = {}
    markdown_text = "\n".join(lines)
    markdown_text = re.sub(r'\n{3,}', '\n\n', markdown_text).strip()
    markdown_text = _idml_insert_precautions_heading(markdown_text)
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


def _prepare_pipeline_source(source_format, kept_source_path):
    """Return a working source path. kept_source_path itself is never deleted here."""
    if source_format != "idml":
        return kept_source_path
    try:
        resolved = _resolve_idml_source(kept_source_path)
    except Exception:
        resolved = None
    if not resolved:
        return None
    if os.path.abspath(resolved) == os.path.abspath(kept_source_path):
        work_path = os.path.join(
            UPLOAD_DIR, f"idml_{int(time.time() * 1000)}_{os.path.basename(kept_source_path)}"
        )
        shutil.copy2(kept_source_path, work_path)
        return work_path
    return resolved


def _requirements_with_feedback(requirements, feedback):
    base = re.sub(r"(?m)^\s*\[IME反馈\].*$", "", requirements or "")
    base = re.sub(r"\n{3,}", "\n\n", base).strip()
    feedback = (feedback or "").strip()
    if not feedback:
        return base
    if base:
        return f"{base}\n[IME反馈] {feedback}"
    return f"[IME反馈] {feedback}"


def _convert_chat_fn():
    try:
        from app.utils.ai_client import ai_client
        return ai_client.chat
    except Exception:
        return None


def _apply_feedback_to_output_zip(zip_path, feedback, screenshot_path=None):
    from app.utils.convert_feedback import apply_convert_feedback_to_zip
    return apply_convert_feedback_to_zip(
        zip_path, feedback, chat_fn=_convert_chat_fn(), screenshot_path=screenshot_path
    )


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


def _is_cover_topic_xml(xml):
    text = xml or ""
    return bool(
        re.search(r'cms:imesofttype\s*=\s*["\']sCoverTopic["\']', text, re.I)
        or re.search(r'outputclass\s*=\s*["\']cover["\']', text, re.I)
    )


def _product_name_from_filename(file_path):
    stem = os.path.splitext(os.path.basename(file_path or ""))[0]
    stem = COVER_PART_NO_RE.sub(" ", stem)
    stem = re.sub(r'(?i)\b(?:ifu|instructions for use|ce|ruo|kit)\b', " ", stem)
    stem = re.sub(r'[-_]+', " ", stem)
    return re.sub(r'\s+', " ", stem).strip(" ._-") or None


def _cover_manual_name(blob, dita_lang="en-US"):
    text = blob or ""
    lang_zh = str(dita_lang or "").lower().startswith("zh")
    if _is_system_guide_source(source_content=text):
        return "系统操作指南" if lang_zh else "System Guide"
    if re.search(r"(?i)user\s+manual|用户手册", text):
        return "用户手册" if lang_zh else "User Manual"
    return "使用说明书" if lang_zh else "Instructions for Use"


def _extract_cover_fields(file_path, source_content="", dita_lang="en-US"):
    """Fill cover Part No., manual name, version, model, and product name."""
    fields = {}
    blob = "\n".join(
        part for part in (os.path.basename(file_path or ""), source_content or "") if part
    )
    part_match = COVER_PART_NO_RE.search(blob)
    if part_match:
        fields["part_no"] = part_match.group(1)

    lang = (dita_lang or "").lower()
    fields["manual_name"] = _cover_manual_name(blob, dita_lang)
    if lang.startswith("zh"):
        product_match = re.search(r'本(?:说明书|指南)适用于\s*([^。\n]+)', source_content or "")
    else:
        product_match = re.search(
            r'(?i)(?:this\s+)?(?:instructions for use|user manual|guide) is applicable to\s+([^.]+)',
            source_content or "",
        )
        if not product_match:
            product_match = re.search(r'(?i)applicable to\s+([^.]+)', source_content or "")

    if product_match:
        product = re.sub(r'\s+', " ", product_match.group(1)).strip(" .")
        product = re.sub(r'\s+set$', " Set", product, flags=re.I)
        fields["product_name"] = product
    else:
        fallback = _product_name_from_filename(file_path)
        if fallback:
            fields["product_name"] = fallback

    version_match = re.search(
        r'(?i)(?:manual version|version of the (?:instructions for use|user manual|guide))\s*(?:is|:)\s*(v?\d+(?:\.\d+)*)',
        source_content or "",
    )
    if not version_match:
        version_match = re.search(
            r'(?:手册)?版本(?:为|是|:|：)\s*(v?\d+(?:\.\d+)*)',
            source_content or "",
            re.I,
        )
    if version_match:
        fields["version"] = version_match.group(1)

    model_match = re.search(r'(?i)DNBSEQ-([A-Za-z0-9+]+)', blob)
    if model_match:
        fields["product_model"] = model_match.group(1)
    return fields


def _replace_cover_value_after_label(xml, label_pattern, value):
    if not xml or not value:
        return xml
    escaped = _escape_xml_attr(value)
    pattern = re.compile(
        rf'(<p\b[^>]*>\s*(?:{label_pattern})\s*</p>\s*</entry>\s*<entry\b[^>]*>\s*)'
        r'(<p\b[^>]*/>|<p\b[^>]*>.*?</p>)',
        re.DOTALL | re.I,
    )

    def _repl(match):
        p_tag = match.group(2)
        attr_match = re.match(r'<p(\b[^>]*?)(?:\s*/)?>', p_tag, re.I)
        attr = attr_match.group(1) if attr_match else ""
        attr = re.sub(r'\s*/\s*$', "", attr)
        return f'{match.group(1)}<p{attr}>{escaped}</p>'

    return pattern.sub(_repl, xml, count=1)


def _patch_template_cover_fields(cover_xml, fields):
    if not cover_xml or not fields:
        return cover_xml
    xml = cover_xml
    xml = _replace_cover_value_after_label(xml, r'Part\s*No\.?', fields.get("part_no"))
    xml = _replace_cover_value_after_label(xml, r'手册编号', fields.get("part_no"))
    xml = _replace_cover_value_after_label(xml, r'编号', fields.get("part_no"))
    xml = _replace_cover_value_after_label(xml, r'Serial\s+number', fields.get("part_no"))
    xml = _replace_cover_value_after_label(xml, r'手册名称', fields.get("manual_name"))
    xml = _replace_cover_value_after_label(xml, r'Item', fields.get("manual_name"))
    xml = _replace_cover_value_after_label(xml, r'产品名称[^<]*', fields.get("product_name"))
    xml = _replace_cover_value_after_label(xml, r'Version', fields.get("version"))
    xml = _replace_cover_value_after_label(xml, r'版本', fields.get("version"))
    xml = _replace_cover_value_after_label(xml, r'Product\s+model', fields.get("product_model"))
    xml = _replace_cover_value_after_label(xml, r'产品型号', fields.get("product_model"))
    xml = _replace_cover_value_after_label(xml, r'型号', fields.get("product_model"))
    return xml


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


def _content_to_dita_xml(section_title, section_content, dita_type, topic_id, dita_lang, level=2, topic_kind="concept", source_format="docx", xref_map=None, is_system_guide=False):
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

    def _restore_stashed_image(idx_text):
        try:
            idx = int(idx_text)
        except (TypeError, ValueError):
            return None
        if 0 <= idx < len(image_stash):
            href = image_stash[idx]["href"]
            return f'<image href="{_escape_xml_attr(href)}"></image>'
        return None

    def _restore_inline_run_markup(text, in_step=False):
        restored = text or ''
        def _img_token(match):
            xml = _restore_stashed_image(match.group(1))
            return xml if xml is not None else match.group(0)
        restored = IMG_PLACEHOLDER_ANY_RE.sub(_img_token, restored)
        parts = []
        last = 0
        for match in _iter_md_images(restored):
            parts.append(restored[last:match.start()])
            parts.append(f'<image href="{_escape_xml_attr(match.group(2))}"></image>')
            last = match.end()
        parts.append(restored[last:])
        restored = "".join(parts)
        if in_step and is_english and not is_native_md:
            # In English operation steps a bold run names a UI control.
            restored = re.sub(r'\[\[B\]\](.*?)\[\[/B\]\]', r'<uicontrol>\1</uicontrol>', restored)
        else:
            restored = re.sub(r'\[\[B\]\](.*?)\[\[/B\]\]', r'<b>\1</b>', restored)
        restored = re.sub(r'\[\[SUP\]\](.*?)\[\[/SUP\]\]', r'<sup>\1</sup>', restored)
        restored = re.sub(r'\[\[SUB\]\](.*?)\[\[/SUB\]\]', r'<sub>\1</sub>', restored)
        restored = re.sub(r'\[\[I\]\](.*?)\[\[/I\]\]', r'<i>\1</i>', restored)
        restored = re.sub(r'\[\[TERM\]\](.*?)\[\[/TERM\]\]', r'<term>\1</term>', restored)
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
        restored = re.sub(r'\[\[/?TERM\]\]', '', restored)
        restored = UI_CONTROL_RE.sub(r'<uicontrol>\1</uicontrol>', restored)
        if is_english:
            def _en_bracket_ui(match):
                inner = match.group(1).strip()
                if not inner or inner in {
                    "B", "/B", "SUP", "/SUP", "SUB", "/SUB", "UI", "/UI",
                    "I", "/I", "CODE", "/CODE", "LINK", "/LINK",
                    "TERM", "/TERM",
                    "UL", "/UL", "OL", "/OL", "LI", "/LI",
                    "P",
                } or inner.startswith((
                    "XREF:", "NOTE:", "TABCAP", "FIGCAP", "TWIDE:",
                    "INDEX:",
                    "COLW:", "THEAD:", "LVL:", "SPAN:",
                    "BG:", "KEEP",
                )):
                    return match.group(0)
                return f'<uicontrol>{inner}</uicontrol>'
            restored = EN_BRACKET_UI_RE.sub(_en_bracket_ui, restored)
        # InDesign cross-reference -> empty <xref cms:title="..."/>. IME fills
        # the visible quote/page text from the target topic.
        def _xref_repl(match):
            target = match.group(1).strip()
            display = _clean_xref_title(target) or target
            if _caption_xref_kind(display) or _caption_xref_kind(target):
                return f'<xref cms:title="{_escape_xml_attr(display)}"/>'
            target_id = _xref_map_get(xref_map, target) or _xref_map_get(xref_map, display)
            if target_id:
                return (
                    f'<xref href="{_escape_xml_attr(target_id)}.dita" '
                    f'cms:title="{_escape_xml_attr(display)}"/>'
                )
            return f'<xref cms:title="{_escape_xml_attr(display)}"/>'
        restored = XREF_RE.sub(_xref_repl, restored)
        def _index_repl(match):
            terms = [part.strip() for part in (match.group(1) or "").split("/") if part.strip()]
            if not terms:
                return ""
            return (
                "".join(f"<indexterm>{_escape_xml_attr(term)}" for term in terms)
                + "</indexterm>" * len(terms)
            )
        restored = INDEX_RE.sub(_index_repl, restored)
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
        # IME draws 【】 around uicontrol, so source spaces around the run
        # become a double gap. Drop the adjacent spaces.
        restored = re.sub(
            r'[ \t]*((?:<uicontrol>.*?</uicontrol>)+)[ \t]*',
            r'\1',
            restored,
        )
        restored = _unwrap_italic_punct_after_xref(restored)
        return restored

    def _split_keep_marker(text):
        raw = text or ""
        if raw.startswith(IDML_KEEP_MARKER):
            return True, raw[len(IDML_KEEP_MARKER):].lstrip()
        return False, raw

    def _paragraph_xml(text, indent="        "):
        keep, raw = _split_keep_marker(text)
        attr = ' outputclass="keep"' if keep else ""
        parts = _split_idml_p_parts(raw)
        if not parts:
            return f"{indent}<p{attr}></p>"
        if len(parts) == 1:
            return f"{indent}<p{attr}>{_restore_inline_run_markup(parts[0])}</p>"
        return "\n".join(
            f"{indent}<p{attr if index == 0 else ''}>{_restore_inline_run_markup(part)}</p>"
            for index, part in enumerate(parts)
        )

    section_content, image_stash = _stash_md_images(section_content)

    def _match_md_image_line(text):
        stripped = (text or "").strip()
        token = IMG_PLACEHOLDER_RE.match(stripped)
        if token:
            try:
                idx = int(token.group(1))
            except (TypeError, ValueError):
                return None
            if 0 <= idx < len(image_stash):
                item = image_stash[idx]
                return _MdImageMatch(item["alt"], item["href"], 0, len(stripped))
            return None
        match = _parse_md_image_at(stripped, 0)
        if not match or stripped[match.end():].strip():
            return None
        return match

    safe_content = section_content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("<br>", "")

    table_rows = []
    in_table = False
    list_items = []
    in_list = False
    list_type = None
    list_base_level = 0
    list_note_type = None
    pending_table_header_rows = None
    pending_table_wide = None
    pending_table_colwidths = None
    in_codeblock = False
    codeblock_lang = ""
    codeblock_lines = []
    codeblock_indent = ""

    def _flush_list():
        nonlocal in_list, list_items, list_type, list_base_level, list_note_type
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
                    if item.get("prewrapped"):
                        rendered.append(f"{indent}  <li>{item['text']}")
                    else:
                        rendered.append(f"{indent}  <li><p>{item['text']}</p>")
                    if child_blocks:
                        rendered.append(child_blocks)
                    if children:
                        rendered.append(children.lstrip("\n"))
                    if trailing:
                        rendered.append(trailing)
                    rendered.append(f"{indent}  </li>")
                else:
                    if item.get("prewrapped"):
                        rendered.append(f"{indent}  <li>{item['text']}</li>")
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
        note_type = list_note_type
        list_note_type = None
        if note_type and result and pending_note_type is None:
            result = f'        <note type="{note_type}">\n{result}\n        </note>'
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
    pending_note_from_icon = False
    pending_note_is_list = False

    def _append_block(xml, default_indent="        "):
        if pending_note_type is not None:
            pending_note_blocks.append(xml)
        elif in_list and list_items:
            _attach_list_xml(xml)
        else:
            body_parts.append(xml)

    def _append_body(xml):
        body_parts.append(xml)

    def _append_list_item(text, level=None, item_type=None, prewrapped=False):
        list_items.append({
            "text": text,
            "prewrapped": prewrapped,
            "blocks": [],
            "children": [],
            "trailing": [],
            "level": level if level is not None else list_base_level,
            "type": item_type or list_type or "ul",
        })

    def _append_restored_list_item(raw_item, level, item_type):
        parts = _split_idml_p_parts(_idml_maybe_regulation_psep(raw_item))
        if len(parts) > 1:
            inner = "".join(
                f"<p>{_restore_inline_run_markup(_clean_output_text(part), in_step=True)}</p>"
                for part in parts
            )
            _append_list_item(inner, level, item_type, prewrapped=True)
            return
        _append_list_item(
            _restore_inline_run_markup(_clean_output_text(raw_item), in_step=True),
            level,
            item_type,
        )

    def _append_list_continuation(xml, hang_level=None):
        """Hang a following paragraph/image on the current parent list item.

        Nested bullets must not steal body that belongs to the outer item.
        If nested items already follow the parent, hang the block after those
        children (trailing). Otherwise append to the parent's ordered blocks
        so the paragraph stays ahead of later notes/figures.
        """
        if not (in_list and list_items):
            body_parts.append(xml)
            return
        _attach_list_xml(xml, continuation=True, hang_level=hang_level)

    def _parent_list_item():
        for item in reversed(list_items):
            item_level = item.get("level")
            if item_level is None or item_level <= list_base_level:
                return item
        return list_items[-1]

    def _nearest_list_item(max_level):
        for item in reversed(list_items):
            item_level = item.get("level")
            if item_level is None or item_level <= max_level:
                return item
        return list_items[-1]

    def _attach_list_xml(xml, continuation=False, hang_level=None):
        """Keep list-item extras in source order.

        Continuation paragraphs go onto the parent item. When the parent is
        still the last item they join ``blocks`` (with notes/figs). After
        nested children exist they join ``trailing``. Later notes/figs follow
        that trailing stream so they stay with the parent-level paragraph.
        """
        last = list_items[-1]
        if hang_level is not None:
            target = _nearest_list_item(hang_level)
            last_level = last.get("level")
            if (
                continuation
                and last_level is not None
                and last_level == hang_level
                and last_level > (list_base_level or 0)
            ):
                outer = None
                for item in reversed(list_items[:-1]):
                    item_level = item.get("level")
                    if item_level is None or item_level < hang_level:
                        outer = item
                        break
                if outer is not None:
                    outer.setdefault("trailing", []).append(xml)
                    return
            if target is last:
                target["blocks"].append(xml)
            else:
                target.setdefault("trailing", []).append(xml)
            return
        parent = _parent_list_item()
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
        if _note_type_from_icon_href(path):
            return True
        if not path or path.startswith(("http://", "https://")) or not os.path.exists(path):
            return False
        try:
            from PIL import Image
            with Image.open(path) as img:
                width, height = img.size
            return width <= 220 and height <= 120
        except Exception:
            return False

    def _leading_image(text):
        remaining = text or ""
        skip = len(remaining) - len(remaining.lstrip())
        body = remaining[skip:]
        token = IMG_PLACEHOLDER_ANY_RE.match(body)
        if token:
            try:
                idx = int(token.group(1))
            except (TypeError, ValueError):
                return None
            if 0 <= idx < len(image_stash):
                item = image_stash[idx]
                return item["alt"], item["href"], skip + token.end()
            return None
        match = _parse_md_image_at(body, 0)
        if not match:
            return None
        return match.group(1), match.group(2), skip + match.end()

    def _strip_leading_note_icons(text):
        remaining = text or ""
        had_icon = False
        while True:
            parsed = _leading_image(remaining)
            if not parsed:
                break
            _alt, href, end = parsed
            if not _is_note_icon_image(href):
                break
            had_icon = True
            remaining = remaining[end:]
        return remaining.strip(), had_icon

    def _infer_note_type_from_text(text):
        normalized = _strip_md_bold(_unescape_md(_strip_list_prefix((text or '').strip()))).lower()
        if any(keyword in normalized for keyword in ["warning", "caution", "danger", "请勿", "切勿", "警告", "小心", "do not"]):
            return "warning"
        if normalized.startswith("注意"):
            return "caution"
        return "tip"

    def _flush_pending_note(text=None):
        nonlocal pending_note_type, pending_note_label, pending_note_blocks, note_icon_detected
        nonlocal pending_note_from_icon, pending_note_is_list
        if pending_note_type is None:
            return None
        body = (text or "").strip().lstrip('.:：;； ').strip()
        if body:
            pending_note_blocks.append(f'          <p>{_restore_inline_run_markup(body)}</p>')
        if not pending_note_blocks:
            fallback = pending_note_label or ""
            pending_note_blocks.append(f'          <p>{_restore_inline_run_markup(fallback)}</p>')
        if pending_note_is_list:
            lis = []
            extras = []
            for block in pending_note_blocks:
                if "<li>" in block:
                    lis.append(block)
                else:
                    extras.append(block)
            inner_parts = []
            if lis:
                inner_parts.append("          <ul>\n" + "\n".join(lis) + "\n          </ul>")
            inner_parts.extend(extras)
            inner = "\n".join(inner_parts)
        else:
            inner = "\n".join(_group_note_enumerated_blocks(pending_note_blocks))
        note_xml = f'        <note type="{pending_note_type}">\n{inner}\n        </note>'
        pending_note_type = None
        pending_note_label = None
        pending_note_blocks = []
        note_icon_detected = False
        pending_note_from_icon = False
        pending_note_is_list = False
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
            if not _match_md_image_line(candidate):
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

    def _flush_pending_image(wrap_fig=True):
        nonlocal pending_image
        if not pending_image:
            return None
        image_xml = f'<image href="{_escape_xml_attr(pending_image["href"])}"></image>'
        pending_image = None
        if wrap_fig:
            return f'        <fig>{image_xml}</fig>'
        return f'        {image_xml}'

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

    def _absorb_legend_table(table_xml):
        """Move an untitled parts table into the preceding fig or image table."""
        idx = len(body_parts) - 1
        while idx >= 0:
            part = (body_parts[idx] or "").strip()
            if (not part) or part.startswith("<note"):
                idx -= 1
                continue
            break
        if idx < 0:
            return False
        stripped = body_parts[idx].rstrip()
        if stripped.endswith("</fig>"):
            body_parts[idx] = stripped[:-6].rstrip() + "\n" + table_xml + "\n        </fig>"
            return True
        if "<table" not in stripped or not stripped.endswith("</table>"):
            return False
        entries = re.findall(r"<entry\b[^>]*>(.*?)</entry>", stripped, re.S)
        if not entries:
            return False
        if not all(("<image" in entry) or (not re.sub(r"<[^>]+>", "", entry).strip()) for entry in entries):
            return False
        images = re.findall(r"<image\b[^>]*(?:/>|>.*?</image>)", stripped)
        if not images:
            return False
        title_match = re.search(r"<title[^>]*>.*?</title>", stripped, re.S)
        title_xml = title_match.group(0) if title_match else ""
        fig = "        <fig>"
        if title_xml:
            fig += title_xml
        fig += "".join(images) + "\n" + table_xml + "\n        </fig>"
        body_parts[idx] = fig
        return True

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

        def _dita_p_xml(text, in_step=False):
            parts = _split_idml_p_parts(text)
            if not parts:
                return "<p></p>"
            return "".join(
                f"<p>{_restore_inline_run_markup(part, in_step=in_step)}</p>"
                for part in parts
            )

        def _dita_li_xml(item):
            item = (item or "").strip()
            if not item:
                return "<li><p></p></li>"
            if IDML_NESTED_NOTE_RE.search(item):
                parts = []
                cursor = 0
                for note_match in IDML_NESTED_NOTE_RE.finditer(item):
                    before = item[cursor:note_match.start()].strip()
                    if before:
                        parts.append(_dita_p_xml(before))
                    parts.append(
                        f'<note type="{note_match.group(1)}">{_dita_note_inner_xml(note_match.group(2).strip())}</note>'
                    )
                    cursor = note_match.end()
                tail = item[cursor:].strip()
                if tail:
                    parts.append(_dita_p_xml(tail))
                return f"<li>{''.join(parts) or '<p></p>'}</li>"
            return f"<li>{_dita_p_xml(item)}</li>"

        def _dita_note_inner_xml(body):
            """Rebuild note inner XML from [[UL]] markers or a plain paragraph."""
            text = (body or "").strip()
            chunks = []
            list_re = re.compile(
                re.escape(IDML_CELL_UL_OPEN)
                + r"(.*?)"
                + re.escape(IDML_CELL_UL_CLOSE)
                + r"|"
                + re.escape(IDML_CELL_OL_OPEN)
                + r"(.*?)"
                + re.escape(IDML_CELL_OL_CLOSE),
                re.S,
            )
            pos = 0
            for match in list_re.finditer(text):
                before = text[pos:match.start()].strip()
                if before:
                    chunks.append(_dita_p_xml(before))
                tag = "ul" if match.group(0).startswith(IDML_CELL_UL_OPEN) else "ol"
                inner = match.group(1) if tag == "ul" else match.group(2)
                items = [item for item in (inner or "").split(IDML_CELL_LIST_SEP) if item.strip()]
                lis = "".join(
                    _dita_li_xml(item) for item in items
                )
                if lis:
                    chunks.append(f"<{tag}>{lis}</{tag}>")
                pos = match.end()
            tail = text[pos:].strip()
            if tail:
                chunks.append(_dita_p_xml(tail))
            if not chunks:
                return "<p></p>"
            return "".join(chunks)

        def _dita_table_entry_xml(cell_text, attrs=""):
            stripped = (cell_text or "").strip()
            bg_match = IDML_BG_MARK_RE.search(stripped)
            if bg_match:
                attrs += f' vf:bgcolor="{bg_match.group(1)}"'
                stripped = IDML_BG_MARK_RE.sub("", stripped).strip()
                cell_text = IDML_BG_MARK_RE.sub("", cell_text or "")
            if IDML_FIGCAP_MARKER in stripped:
                img_part, cap_part = stripped.split(IDML_FIGCAP_MARKER, 1)
                caption = _strip_figure_number(
                    _normalize_figure_title(IDML_FIGCAP_MARKER + cap_part.strip())
                )
                img_xml = _restore_inline_run_markup(img_part.strip())
                title_xml = f"<title>{_escape_xml_text(caption)}</title>" if caption else ""
                if "valign=" not in attrs:
                    attrs += ' valign="bottom"'
                return f"<entry{attrs}><fig>{title_xml}{img_xml}</fig></entry>"
            ul = stripped.startswith(IDML_CELL_UL_OPEN) and stripped.endswith(IDML_CELL_UL_CLOSE)
            ol = stripped.startswith(IDML_CELL_OL_OPEN) and stripped.endswith(IDML_CELL_OL_CLOSE)
            if ul or ol:
                inner = stripped[len(IDML_CELL_UL_OPEN if ul else IDML_CELL_OL_OPEN):
                                 -len(IDML_CELL_UL_CLOSE if ul else IDML_CELL_OL_CLOSE)]
                items = [i for i in inner.split(IDML_CELL_LIST_SEP) if i.strip()]
                tag = "ul" if ul else "ol"
                lis = "".join(
                    _dita_li_xml(i) for i in items
                )
                return f"<entry{attrs}><{tag}>{lis}</{tag}></entry>"
            if IDML_NESTED_NOTE_RE.search(stripped):
                chunks = []
                cursor = 0
                for note_match in IDML_NESTED_NOTE_RE.finditer(stripped):
                    before = stripped[cursor:note_match.start()].strip()
                    if before:
                        chunks.append(("p", before))
                    chunks.append(("note", note_match.group(1), note_match.group(2).strip()))
                    cursor = note_match.end()
                tail = stripped[cursor:].strip()
                if tail:
                    chunks.append(("p", tail))
                inner_xml = []
                for chunk in chunks:
                    if chunk[0] == "p":
                        para_xml = _dita_p_xml(chunk[1])
                        if para_xml and para_xml != "<p></p>":
                            inner_xml.append(para_xml)
                    else:
                        inner_xml.append(
                            f'<note type="{chunk[1]}">{_dita_note_inner_xml(chunk[2])}</note>'
                        )
                if not inner_xml:
                    return f"<entry{attrs}></entry>"
                return f"<entry{attrs}>{''.join(inner_xml)}</entry>"
            if IDML_CELL_UL_OPEN in stripped or IDML_CELL_OL_OPEN in stripped:
                return f"<entry{attrs}>{_dita_note_inner_xml(stripped)}</entry>"
            restored = _restore_inline_run_markup(cell_text or "")
            if not restored.strip():
                return f"<entry{attrs}></entry>"
            if IDML_CELL_P_SEP in stripped:
                return f"<entry{attrs}>{_dita_p_xml(stripped)}</entry>"
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
        if header_rows == 0 and filtered_rows and filtered_rows[0]:
            first = filtered_rows[0][0]
            span = _table_cell_rowspan(first)
            if span > 1 and span >= len(filtered_rows) and "[[BG:" not in (first or ""):
                filtered_rows = [list(row) for row in filtered_rows]
                filtered_rows[0][0] = f"[[BG:#C0C0C0]]{first}"
        title_text = ""
        if has_title:
            title_text = _restore_inline_run_markup(_normalize_table_title(pending_table_title or _strip_tag(prev)))
        wide = pending_table_wide or (
            "180mm" if _dita_table_should_be_extra_wide(cols, section_title, title_text) else None
        )
        pending_table_wide = None
        table_attr = f' outputclass="{_dita_format_mm_width(wide)}"' if wide else ""
        if has_title:
            table_xml = [f'        <table{table_attr}>', f'          <title>{title_text}</title>']
        else:
            table_xml = [f'        <table{table_attr}>']

        rowheader = ""
        hay = f"{section_title or ''} {title_text or ''}".lower()
        if "test results of genetic sequencer" in hay:
            rowheader = ' rowheader="firstcol"'
        table_xml.append(f'          <tgroup cols="{cols}"{rowheader}>')
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
        xml = "\n".join(table_xml)
        if _is_untitled_parts_legend_table(filtered_rows, has_title) and _absorb_legend_table(xml):
            return None
        return xml

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
                image_xml = _flush_pending_image(wrap_fig=False)
                if image_xml:
                    _append_block(image_xml)
            table_xml = _flush_pending_table()
            if table_xml:
                _append_block(table_xml)
            _append_body("")
            continue

        current_image_match = _match_md_image_line(stripped)
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
                image_xml = _flush_pending_image(wrap_fig=False)
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
                next_image = _match_md_image_line(_next_nonempty_line(safe_lines, idx))
                if not next_image:
                    figure_xml = _flush_pending_figure()
                    if figure_xml:
                        _append_block(figure_xml)
                continue
            note_type = _note_type_from_icon_href(href)
            next_nonempty = _next_nonempty_line(safe_lines, idx)
            next_is_list = bool(re.match(r"^\s*(?:[-*+]|\d+[.)])\s+", next_nonempty))
            next_is_note_body = bool(
                next_nonempty
                and not _match_md_image_line(next_nonempty)
                and not next_nonempty.startswith("|")
                and not next_nonempty.startswith("#")
                and not next_nonempty.startswith("[[FIGCAP]]")
                and not next_nonempty.startswith("[[TABCAP]]")
                and not _is_figure_caption(next_nonempty)
            )
            if note_type and (next_is_list or next_is_note_body):
                _flush_pending_note_to_body()
                image_xml = _flush_pending_image()
                if image_xml:
                    _append_block(image_xml)
                pending_note_type = note_type
                pending_note_from_icon = True
                pending_note_is_list = next_is_list
                pending_image = None
                skip_next_note_icon_image = False
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
                _match_md_image_line(_next_nonempty_line(safe_lines, idx))
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
            if pending_note_type and pending_note_from_icon:
                item = re.sub(r'^\s*[-*+]\s+', '', line)
                pending_note_is_list = True
                pending_note_blocks.append(
                    f'          <li><p>{_restore_inline_run_markup(_clean_output_text(item), in_step=True)}</p></li>'
                )
                continue
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
            item, had_note_icon = _strip_leading_note_icons(item)
            if had_note_icon:
                list_note_type = list_note_type or "tip"
            _append_restored_list_item(item, line_level, "ul")
        elif re.match(r'^\s*\d+[.)]\s+', line):
            next_nonempty = _next_nonempty_line(safe_lines, idx)
            if pending_note_type and pending_note_from_icon:
                item = re.sub(r'^\s*\d+[.)]\s+', '', line)
                pending_note_is_list = True
                pending_note_blocks.append(
                    f'          <li><p>{_restore_inline_run_markup(_clean_output_text(item), in_step=True)}</p></li>'
                )
                continue
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
            _append_restored_list_item(item, line_level, "ol")
        elif re.match(r'^#{1,6}\s+', line):
            _flush_pending_note_to_body()
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
                    pending_note_from_icon = False
                    pending_note_is_list = False
                    continue
                if pending_note_from_icon and pending_note_is_list:
                    _flush_pending_note_to_body()
                else:
                    note_xml = _flush_pending_note(clean)
                    _append_block(note_xml)
                    continue
            next_line = safe_lines[idx + 1].strip() if idx + 1 < len(safe_lines) else ""
            next_image_match = _match_md_image_line(next_line)
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
                note_type = (
                    _note_type_from_icon_href(pending_image.get("href"))
                    or _infer_note_type_from_text(clean)
                )
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
                        _paragraph_xml(clean),
                        hang_level=line_level,
                    )
                    continue
            if re.match(r'^\d+[A-Za-z]?(?:[-–—]\d+)?$', clean):
                continue
            result = _flush_list()
            if result:
                _append_body(result)
            _append_body(_paragraph_xml(clean))

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

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
{doctype}
<{root_tag} xmlns:cms="http://www.w3.org/ime/cms" xmlns:m="http://www.w3.org/1998/Math/MathML" xmlns:vf="http://www.megalinkware.com" xml:lang="{dita_lang}" id="{xml_id}"{outputclass} cms:keys="{topic_id}" cms:title="{safe_title_attr}" cms:number="{topic_id}" cms:imesofttype="{ime_topic_type}">
  <title id="title_{topic_id}">{safe_title}</title>
  <{body_tag} id="body_{topic_id}" outputclass="pretext">
{body_content}
  </{body_tag}>
</{root_tag}>"""
    return _place_indexterms_in_body(xml)


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

    source_about = next(
        (
            topic for topic in topics_output
            if topic.get("filename") and _is_about_manual_title(topic.get("title", ""))
        ),
        None,
    )
    if source_about:
        about_nav = _escape_xml_attr(_clean_navtitle(source_about["title"]))
        if f'navtitle="{about_nav}"' not in rewritten:
            def _retarget_about(match):
                tag = match.group(0)
                tag = re.sub(r'navtitle="[^"]*"', f'navtitle="{about_nav}"', tag)
                tag = re.sub(r'href="[^"]*"', f'href="{source_about["filename"]}"', tag)
                if 'keys="' in tag:
                    tag = re.sub(r'keys="[^"]*"', f'keys="{source_about["id"]}"', tag)
                if 'cms:title="' in tag:
                    tag = re.sub(r'cms:title="[^"]*"', f'cms:title="{about_nav}"', tag)
                if 'cms:placeHolder="' in tag:
                    tag = re.sub(
                        r'cms:placeHolder="[^"]*"',
                        f'cms:placeHolder="{_topic_placeholder(source_about)}"',
                        tag,
                    )
                return tag

            rewritten, replaced = re.subn(
                r'<topicref\b[^>]*navtitle="(?:关于说明书|关于指南|About the user manual|About the instructions for use|About this guide|About the guide)"[^>]*(?:/>|>\s*</topicref>)',
                _retarget_about,
                rewritten,
                count=1,
                flags=re.I,
            )
            if replaced:
                used_files.add(source_about["filename"])

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
                href = html.unescape(href.strip())
                if href.startswith("image/"):
                    referenced.add(href)
            for match in _iter_md_images(content):
                md_path = html.unescape((match.group(2) or "").strip())
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
    # Title-only grouping nodes are IME topicref structure items: no .dita, no href.
    if topic.get("is_container_only") or not _topic_uses_dita_file(topic):
        attrs = (
            f'navtitle="{navtitle}" '
            f'xml:lang="{dita_lang}" id="{node_id}" '
            f'applicDesc="" '
            f'cms:title="{navtitle}" '
            f'cms:placeHolder="" '
            f'cms:nodeType="" '
            f'cms:template="" '
            f'level="{level_attr}" '
            f'cms:imesofttype="" '
            f'version="{GENERATED_NODE_VERSION}"'
        )
    else:
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


def _append_backmatter_index_xml(lines, indent, timestamp, dita_lang):
    """IME builds the index page from backmatter > booklists > indexlist."""
    backmatter_id = f"PG{timestamp}_BM"
    booklists_id = f"PG{timestamp}_IBL"
    indexlist_id = f"PG{timestamp}_IX"
    lines.append(
        f'{indent}<backmatter navtitle="Backmatter" id="{backmatter_id}" applicDesc=""'
        f' cms:lang="{dita_lang}" cms:title="" cms:placeHolder="" cms:isTemplet="N"'
        f' cms:referenceType="" cms:type="backmatter" cms:outputclass=""'
        f' cms:descriptioin="" cms:xCoordination="" cms:sourceTag=""'
        f' cms:referenceMap="" cms:colNumber="2" cms:nodeRemark=""'
        f' level="1" version="{GENERATED_NODE_VERSION}">'
    )
    lines.append(
        f'{indent}  <booklists id="{booklists_id}" applicDesc="" cms:lang="{dita_lang}" cms:title="" cms:placeHolder=""'
        f' cms:isTemplet="N" cms:referenceType="" cms:type="booklists" cms:outputclass=""'
        f' cms:descriptioin="" cms:xCoordination="" cms:sourceTag="" cms:referenceMap=""'
        f' cms:colNumber="2" cms:nodeRemark="" level="2" version="{GENERATED_NODE_VERSION}">'
    )
    lines.append(
        f'{indent}    <indexlist id="{indexlist_id}" applicDesc="" cms:lang="{dita_lang}" cms:title="" cms:placeHolder=""'
        f' cms:isTemplet="N" cms:referenceType="" cms:type="indexlist" cms:outputclass=""'
        f' cms:descriptioin="" cms:xCoordination="" cms:sourceTag="" cms:referenceMap=""'
        f' cms:colNumber="2" cms:nodeRemark="" level="3" version="{GENERATED_NODE_VERSION}"/>'
    )
    lines.append(f'{indent}  </booklists>')
    lines.append(f'{indent}</backmatter>')


def _append_bookmap_topics(lines, topic_roots, timestamp, dita_lang):
    chapter_seq = iter(range(1, 10000))
    node_id_seq = iter(range(1, 100000))

    cover_node = None
    frontmatter_nodes = []
    chapter_roots = []
    has_index = False
    for root in topic_roots:
        topic = root["topic"]
        if _normalize_section_key(topic.get("title", "")) == "cover":
            cover_node = root
        elif _is_index_title(topic.get("title", "")) or topic.get("is_index_list"):
            has_index = True
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

    if has_index:
        _append_backmatter_index_xml(lines, "  ", timestamp, dita_lang)


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


def _is_system_guide_source(file_path="", source_content="", title=""):
    """True for 系统操作指南 / System Guide; False for 快速操作指南 and IFU."""
    haystack = " ".join(
        part for part in (
            os.path.basename(file_path or ""),
            title or "",
            (source_content or "")[:4000],
        )
        if part
    )
    if re.search(r"系统操作指南", haystack):
        return True
    if re.search(r"(?i)quick\s*(start|operation)?\s*guide|快速操作指南", haystack):
        return False
    return bool(re.search(r"(?i)\bsystem\s+(operation\s+)?guide\b", haystack))


def _should_limit_dita_image_widths(is_system_guide):
    # Source images already carry frame/SVG size; do not clamp to 150/143/6 mm.
    return False


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


def _should_emit_container_only(section, is_system_guide=False):
    if is_system_guide:
        return False
    if not section.get("has_children"):
        return False

    if (section.get("content") or "").strip():
        return False

    return True


def _build_xref_map(prepared, is_system_guide=False):
    """Map heading titles to topic ids, including container -> first child."""
    xref_map = {}
    for index, (section, title, _dtype, tid, _fname, _kind) in enumerate(prepared or []):
        if _is_index_title(title):
            continue
        if _should_emit_container_only(section, is_system_guide=is_system_guide):
            child_id = None
            for later_section, later_title, _, later_id, _, _ in prepared[index + 1:]:
                if _is_index_title(later_title):
                    continue
                if _should_emit_container_only(later_section, is_system_guide=is_system_guide):
                    continue
                child_id = later_id
                break
            if child_id:
                _xref_map_put(xref_map, title, child_id)
                _xref_map_put(xref_map, _clean_title(section.get("title") or ""), child_id)
            continue
        _xref_map_put(xref_map, title, tid)
        _xref_map_put(xref_map, _clean_title(section.get("title") or ""), tid)
        number = _heading_number(section.get("title") or "")
        if number:
            xref_map.setdefault(number, tid)
        if tid and title:
            xref_map.setdefault(tid, title)
    return xref_map


def _run_pipeline(task_id, db_session_factory, source_format, file_path, source_content,
                   target_format, template_path, requirements_text, output_language=None,
                   post_feedback=None, post_screenshot_path=None):
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

        source_content = _load_source_content(source_format, file_path, source_content)
        is_system_guide = _is_system_guide_source(file_path, source_content)

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

            xref_map = _build_xref_map(prepared, is_system_guide=is_system_guide)

            for section, title, dita_type, topic_id, topic_filename, topic_kind in prepared:
                if _is_index_title(title):
                    topics_output.append({
                        "type": dita_type,
                        "filename": "",
                        "id": "",
                        "topic_kind": topic_kind,
                        "level": section.get("level", 1),
                        "content": "",
                        "raw_content": "",
                        "is_container_only": True,
                        "is_index_list": True,
                        "is_appendix": False,
                        "title": title,
                    })
                    conversion_detail.append({
                        "source_section": title,
                        "target_type": "indexlist",
                        "topic_file": "",
                        "status": "ok",
                    })
                    continue
                if _should_emit_container_only(section, is_system_guide=is_system_guide):
                    topics_output.append({
                        "type": dita_type,
                        "filename": "",
                        "id": "",
                        "topic_kind": topic_kind,
                        "level": section.get("level", 1),
                        "content": "",
                        "raw_content": section["content"],
                        "is_container_only": True,
                        "is_appendix": section.get("is_appendix", False),
                        "title": title,
                    })
                    conversion_detail.append({
                        "source_section": title,
                        "target_type": "topicref",
                        "topic_file": "",
                        "status": "ok",
                    })
                    continue
                dita_content = _content_to_dita_xml(
                    title,
                    section["content"],
                    dita_type,
                    topic_id,
                    dita_lang,
                    topic_kind=topic_kind,
                    source_format=source_format,
                    xref_map=xref_map,
                    is_system_guide=is_system_guide,
                )
                if _is_version_history_topic(dita_content) or (title or "").strip().lower() in _VERSION_HISTORY_TITLES:
                    dita_content = _transpose_version_column_table(dita_content)

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

        _set_progress(76, "验证")

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
                markdown_content = _rewrite_md_image_hrefs(markdown_content, url_map)
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
                            text_content = _rewrite_xml_language_attrs(text_content, dita_lang)
                            if _is_cover_topic_xml(text_content):
                                cover_source = "\n".join(
                                    part for part in (source_content or "", skipped_cover_content or "") if part
                                )
                                cover_fields = _extract_cover_fields(file_path, cover_source, dita_lang)
                                text_content = _patch_template_cover_fields(text_content, cover_fields)
                            if _is_version_history_topic(text_content):
                                text_content = _transpose_version_column_table(text_content)
                            content = text_content.encode("utf-8")
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
                content = _rewrite_dita_image_hrefs(content, url_map)
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
            if source_format == "idml":
                sidecar = os.path.join(
                    os.path.splitext(file_path)[0] + "_idml_media",
                    "_image_placed_mm.json",
                )
                size_map = {}
                if os.path.isfile(sidecar):
                    try:
                        with open(sidecar, encoding="utf-8") as handle:
                            size_map = json.load(handle) or {}
                    except Exception:
                        size_map = {}
                _apply_dita_placed_image_sizes(output_base, size_map)
                _apply_dita_flow_and_symbol_sizes(output_base)
            if _should_limit_dita_image_widths(is_system_guide):
                _apply_dita_inline_icon_widths(output_base)
                _apply_dita_image_page_widths(output_base)
                _apply_dita_overflow_image_widths(output_base)
            _postprocess_dita_topics(output_base)

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

        _set_progress(78, "验证")
        template_check = {
            "name": "模板一致性",
            "status": "passed",
            "detail": "未使用参考模板",
        }
        if template_path and os.path.exists(template_path):
            if target_format == "dita":
                template_check["detail"] = "已复用参考模板 Cover / toc"
            else:
                template_check["detail"] = f"{target_format.upper()} 输出不使用模板包"
        language_check = {
            "name": "语言标记",
            "status": "passed",
            "detail": dita_lang,
        }
        if is_lossless_md_csv:
            overall = "passed"
            checks = [
                {"name": "结构完整性", "status": "passed", "detail": "已按逐行无损格式转换"},
                template_check,
                language_check,
            ]
        else:
            overall, checks = verify_output_dir(output_base, target_format)
            checks = [template_check, language_check] + list(checks or [])
            if any(item.get("status") == "failed" for item in checks) or any(
                item.get("status") == "warning" for item in checks
            ):
                if overall == "passed":
                    overall = "warning"

        _set_progress(85, "打包")
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

        if post_feedback and target_format == "dita" and not is_lossless_md_csv:
            _set_progress(90, "按反馈修改")
            try:
                _apply_feedback_to_output_zip(zip_path, post_feedback, post_screenshot_path)
            except Exception:
                pass
            output_size = os.path.getsize(zip_path)

        verification_report = {
            "overall": overall,
            "checks": checks,
            "unmapped_sections": [],
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
            previous = _task_store.get(task_id) or {}
            _task_store[task_id] = {
                "progress": previous.get("progress", 0),
                "current_step": previous.get("current_step") or "",
                "status": "failed",
                "error": str(e),
            }
        try:
            update_convert_task_failed(db, task_id, str(e))
        except Exception:
            pass
    finally:
        if source_format == "idml" and file_path:
            try:
                basename = os.path.basename(file_path)
                if basename.startswith("idml_") and str(file_path).lower().endswith(".idml"):
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

    combined_requirements = _requirements_with_feedback(requirements, retry_feedback)

    pipeline_file_path = source_path
    if source_format == "idml":
        pipeline_file_path = _prepare_pipeline_source(source_format, source_path)
        if not pipeline_file_path:
            try:
                os.remove(source_path)
            except Exception:
                pass
            raise HTTPException(status_code=400, detail="压缩包中未找到 .idml 文件；.indd 无法直接解析，请导出 IDML 后重试")

    source_content = ""

    task = create_convert_task(db, ConvertTaskCreate(
        source_filename=source_file.filename,
        source_format=source_format,
        target_format=target_format,
        template_filename=template_filename,
        requirements=combined_requirements,
        retry_feedback=retry_feedback,
        retry_screenshot_path=retry_screenshot_path,
        source_path=source_path,
        template_path=template_path,
        output_language=normalized_output_language,
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
    from app.utils.convert_feedback import apply_convert_feedback_to_zip

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

        _set_progress(15, "按反馈修改")
        task = get_convert_task(db, task_id)
        if not task:
            raise RuntimeError("任务不存在")
        src_zip = _convert_output_disk_path(task)
        if not src_zip or not os.path.exists(src_zip):
            raise RuntimeError("找不到已生成的转换包")

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        _set_progress(45, "按反馈修改")
        _set_progress(80, "打包")
        zip_filename = f"output_revised_{timestamp}_{task_id}.zip"
        zip_path = os.path.join(OUTPUT_DIR, zip_filename)
        shutil.copy2(src_zip, zip_path)
        apply_convert_feedback_to_zip(
            zip_path, feedback, chat_fn=_convert_chat_fn(), screenshot_path=screenshot_path
        )

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
        db.close()


def _run_reconvert_pipeline(task_id, feedback, screenshot_path=None):
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        task = get_convert_task(db, task_id)
        if not task:
            raise RuntimeError("任务不存在")
        kept_source = getattr(task, "source_path", None)
        if not kept_source or not os.path.exists(kept_source):
            raise RuntimeError("源文件已过期，请重新上传后再转；当前只能改已生成的包")
        template_path = getattr(task, "template_path", None)
        if template_path and not os.path.exists(template_path):
            template_path = None
        output_language = getattr(task, "output_language", None)
        combined = _requirements_with_feedback(task.requirements, feedback)
        pipeline_path = _prepare_pipeline_source(task.source_format, kept_source)
        if task.source_format == "idml" and not pipeline_path:
            raise RuntimeError("压缩包中未找到 .idml 文件；.indd 无法直接解析，请导出 IDML 后重试")
        source_format = task.source_format
        target_format = task.target_format
        db.close()
        db = None
        _run_pipeline(
            task_id, None, source_format, pipeline_path, "",
            target_format, template_path, combined, output_language,
            post_feedback=feedback, post_screenshot_path=screenshot_path,
        )
        db = SessionLocal()
        task = get_convert_task(db, task_id)
        if task and task.status == "completed":
            task.requirements = combined
            task.retry_feedback = feedback
            if screenshot_path:
                task.retry_screenshot_path = screenshot_path
            db.commit()
    except Exception as e:
        try:
            if db is None:
                db = SessionLocal()
            update_convert_task_failed(db, task_id, str(e))
        except Exception:
            pass
        with _tasks_lock:
            _task_store[task_id] = {
                "progress": 0, "current_step": "解析", "status": "failed"
            }
    finally:
        if db is not None:
            db.close()


@router.post("/{task_id}/revise", response_model=dict)
async def revise_conversion(
    task_id: str,
    feedback: str = Form(...),
    mode: str = Form("patch"),
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

    mode = (mode or "patch").strip().lower()
    if mode not in ("patch", "reconvert"):
        raise HTTPException(status_code=400, detail="mode 仅支持 patch 或 reconvert")
    if mode == "reconvert":
        source_path = getattr(task, "source_path", None)
        if not source_path or not os.path.exists(source_path):
            raise HTTPException(status_code=400, detail="源文件已过期，请重新上传后再转；当前只能改已生成的包")

    current_step = "解析" if mode == "reconvert" else "按反馈修改"
    update_convert_task_status(db, task_id, "processing", progress=5, current_step=current_step)
    with _tasks_lock:
        _task_store[task_id] = {
            "progress": 5, "current_step": current_step, "status": "processing"
        }

    thread = threading.Thread(
        target=_run_reconvert_pipeline if mode == "reconvert" else _run_revise_pipeline,
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

    failed_assigned = False
    for i, name in enumerate(step_names):
        if task.status == "completed" or task.progress >= step_progress_thresholds[i]:
            step_status = "done"
        elif name == current_step:
            step_status = "failed" if task.status == "failed" else "processing"
            failed_assigned = task.status == "failed"
        elif task.status == "failed" and not failed_assigned:
            step_status = "failed"
            failed_assigned = True
        else:
            step_status = "pending"
        steps.append(StepStatus(name=name, status=step_status))

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
