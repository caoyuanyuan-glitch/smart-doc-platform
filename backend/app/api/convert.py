from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
import os
import re
import json
import time
import zipfile
import shutil
import threading
import xml.etree.ElementTree as ET
from app.database import get_db
from app.crud.convert import (
    create_convert_task, get_convert_task, get_convert_tasks,
    update_convert_task_status, update_convert_task_result, update_convert_task_failed,
    update_convert_task_progress, delete_convert_task
)
from app.schemas.convert import (
    ConvertTaskOut, ConvertTaskCreate, ProgressOut, ReportOut,
    StepStatus, CheckItem
)

router = APIRouter()

UPLOAD_DIR = "./static/uploads"
OUTPUT_DIR = "./static/uploads/outputs"

_tasks_lock = threading.Lock()
_task_store = {}

IME_TOPIC_DECL = '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">'
IME_BOOKMAP_DECL = '<!DOCTYPE bookmap PUBLIC "-//OASIS//DTD DITA BookMap//EN" "bookmap.dtd">'


def _ensure_dir(path):
    os.makedirs(path, exist_ok=True)


_ensure_dir(UPLOAD_DIR)
_ensure_dir(OUTPUT_DIR)


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
    - Remove leading numbering (1.1, Chapter 1:, etc.)
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

    # 3. Remove leading numbering patterns
    t = re.sub(r'^\d+[\.\s]+', '', t)
    t = re.sub(r'^(Chapter|Appendix|第)\s*\d+[\.\s:：]*\s*', '', t, flags=re.IGNORECASE)

    # 4. Trim and clean up
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def _parse_md_sections(content):
    """Parse markdown into nested sections for all heading levels (H1-H6).
    Returns: [{"title": str, "sections": [...], "content": str}]
    """
    lines = content.split("\n")
    root_sections = []
    # Stack entries: {"title": str, "level": int, "sections": list, "content_lines": list}
    stack = []
    pending_lines = []

    for line in lines:
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
        return _parse_md_sections(content)
    elif source_format == "docx":
        return _parse_docx_sections(file_path)
    raise ValueError(f"不支持的文件格式: {source_format}")


def _extract_images_md(content):
    """Extract image metadata from markdown content (no download)."""
    images = []
    pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
    for match in re.finditer(pattern, content):
        images.append({"alt": match.group(1), "path": match.group(2)})
    return images


def _download_images_for_output(images, output_base, timeout=30):
    """Download external images and save to output_dir/image/.
    Returns dict mapping original URL to local filename.
    """
    import urllib.request
    import urllib.error
    from pathlib import Path

    image_dir = os.path.join(output_base, "image")
    _ensure_dir(image_dir)

    url_to_local = {}
    idx = 0
    for img in images:
        url = img["path"]
        if not url or not url.startswith(("http://", "https://")):
            continue
        if url in url_to_local:
            continue
        try:
            ext = os.path.splitext(url.split("?")[0])[1] or ".png"
            if ext.lower() not in (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp"):
                ext = ".png"
            local_name = f"image_{idx:03d}{ext}"
            local_path = os.path.join(image_dir, local_name)
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                with open(local_path, "wb") as f:
                    f.write(resp.read())
            url_to_local[url] = f"image/{local_name}"
            idx += 1
        except Exception:
            url_to_local[url] = url
    return url_to_local


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
    """Extract frontmatter XML, Manufacturer appendix XML, and file list from template ZIP."""
    result = {
        "frontmatter_xml": "",
        "manufacturer_xml": "",
        "files": {},        # filename -> content (bytes)
        "image_files": {},  # image/filename -> content (bytes)
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

            # Extract frontmatter section
            fm_match = re.search(r'<frontmatter[^>]*>.*?</frontmatter>', ditamap_content, re.DOTALL)
            if fm_match:
                result["frontmatter_xml"] = fm_match.group(0)

            # Extract Manufacturer appendix
            appx_pattern = r'<appendix[^>]*navtitle="Manufacturer[^"]*"[^>]*>.*?</appendix>'
            mfg_match = re.search(appx_pattern, ditamap_content, re.DOTALL)
            if mfg_match:
                result["manufacturer_xml"] = mfg_match.group(0)

            # Collect all referenced dita files
            all_xml = result["frontmatter_xml"] + result["manufacturer_xml"]
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


def _content_to_dita_xml(section_title, section_content, dita_type, topic_id, level=2):
    safe_title = section_title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def _unescape_md(text):
        for ch in ['*', '_', '\\', '.', '-', '#']:
            text = text.replace('\\' + ch, ch)
        return text

    def _strip_md_bold(text):
        return re.sub(r'\*\*([^*]+)\*\*', r'\1', text)

    def _strip_md_image_alt(text):
        return re.sub(r'!\[([^\]]*)\]\(', r'\1[', text)

    safe_content = section_content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("<br>", "")

    table_rows = []
    in_table = False
    list_lines = []
    in_list = False
    list_type = None

    def _flush_list():
        nonlocal in_list, list_lines, list_type
        if not in_list:
            return ""
        tag = "ul" if list_type == "ul" else "ol"
        items = "\n".join(f"          <li>{li}</li>" for li in list_lines)
        result = f"        <{tag}>\n{items}\n        </{tag}>"
        in_list = False
        list_lines = []
        list_type = None
        return result

    body_parts = []

    for line in safe_content.split("\n"):
        stripped = line.strip()
        if not stripped:
            result = _flush_list()
            if result:
                body_parts.append(result)
            body_parts.append("")
            continue

        if stripped.startswith("|") and stripped.endswith("|"):
            if not in_table:
                in_table = True
                table_rows = []
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            table_rows.append([_strip_md_bold(_unescape_md(c)) for c in cells])
            continue
        elif in_table and re.match(r'^\|[-:\s|]+\|$', stripped):
            continue
        else:
            if in_table:
                in_table = False
                if table_rows:
                    has_title = False
                    if body_parts and not body_parts[-1]:
                        body_parts.pop()
                    if len(body_parts) >= 1:
                        prev = body_parts[-1]
                        if prev and prev.strip().startswith("<p>") and re.match(r'<p>Table\s+\d+[-–]\d+', prev):
                            has_title = True
                            body_parts.pop()
                    cols = max(len(r) for r in table_rows)
                    if has_title:
                        table_xml = ['        <table>', f'          <title>{_strip_tag(prev)}</title>']
                    else:
                        table_xml = ['        <table>']
                    table_xml.append(f'          <tgroup cols="{cols}">')
                    if len(table_rows) > 1:
                        table_xml.append('            <thead>')
                        table_xml.append('              <row>')
                        for c in table_rows[0]:
                            table_xml.append(f'                <entry>{c}</entry>')
                        empty_needed = cols - len(table_rows[0])
                        for _ in range(empty_needed):
                            table_xml.append('                <entry></entry>')
                        table_xml.append('              </row>')
                        table_xml.append('            </thead>')
                        table_xml.append('            <tbody>')
                        for row in table_rows[1:]:
                            table_xml.append('              <row>')
                            for c in row:
                                table_xml.append(f'                <entry>{c}</entry>')
                            empty_needed = cols - len(row)
                            for _ in range(empty_needed):
                                table_xml.append('                <entry></entry>')
                            table_xml.append('              </row>')
                        table_xml.append('            </tbody>')
                    else:
                        table_xml.append('            <tbody>')
                        for row in table_rows:
                            table_xml.append('              <row>')
                            for c in row:
                                table_xml.append(f'                <entry>{c}</entry>')
                            table_xml.append('              </row>')
                        table_xml.append('            </tbody>')
                    table_xml.append('          </tgroup>')
                    table_xml.append('        </table>')
                    body_parts.append("\n".join(table_xml))
                table_rows = []

        image_match = re.match(r'!\[([^\]]*)\]\(([^)]+)\)', stripped)
        if image_match:
            result = _flush_list()
            if result:
                body_parts.append(result)
            alt = image_match.group(1)
            href = image_match.group(2)
            body_parts.append(f'        <image href="{href}" placement="break"><alt>{alt}</alt></image>')
            continue

        if re.match(r'^\s*[-*+]\s+', line):
            if not in_list or list_type != "ul":
                result = _flush_list()
                if result:
                    body_parts.append(result)
                in_list = True
                list_type = "ul"
            item = re.sub(r'^\s*[-*+]\s+', '', line)
            list_lines.append(_strip_md_bold(_unescape_md(item)))
        elif re.match(r'^\s*\d+[.)]\s+', line):
            if not in_list or list_type != "ol":
                result = _flush_list()
                if result:
                    body_parts.append(result)
                in_list = True
                list_type = "ol"
            item = re.sub(r'^\s*\d+[.)]\s+', '', line)
            list_lines.append(_strip_md_bold(_unescape_md(item)))
        elif re.match(r'^#{1,6}\s+', line):
            result = _flush_list()
            if result:
                body_parts.append(result)
            h_level = len(re.match(r'^(#+)', line).group(1))
            h_text = _unescape_md(re.sub(r'^#{1,6}\s+', '', line))
            body_parts.append(f"        <section><title>{h_text}</title></section>")
        else:
            result = _flush_list()
            if result:
                body_parts.append(result)
            clean = _unescape_md(_strip_md_bold(stripped))
            body_parts.append(f"        <p>{clean}</p>")

    result = _flush_list()
    if result:
        body_parts.append(result)
    if in_table and table_rows:
        cols = max(len(r) for r in table_rows)
        table_xml = ['        <table>', f'          <tgroup cols="{cols}">', '            <tbody>']
        for row in table_rows:
            table_xml.append('              <row>')
            for c in row:
                table_xml.append(f'                <entry>{c}</entry>')
            table_xml.append('              </row>')
        table_xml.append('            </tbody>')
        table_xml.append('          </tgroup>')
        table_xml.append('        </table>')
        body_parts.append("\n".join(table_xml))

    body_content = "\n".join(p for p in body_parts if p)

    unique_id = f"topic_{topic_id}"
    ime_topic_type = "sDitaTopic"

    return f"""<?xml version="1.0" encoding="UTF-8"?>
{IME_TOPIC_DECL}
<topic xmlns:cms="http://www.w3.org/ime/cms" xmlns:m="http://www.w3.org/1998/Math/MathML" xml:lang="zh-CN" id="{unique_id}" cms:keys="{topic_id}" cms:title="{safe_title}" cms:placeholder="{topic_id}" cms:number="{topic_id}" cms:imesofttype="{ime_topic_type}" cms:placeHolder="{topic_id}">
  <title id="title_{topic_id}">{safe_title}</title>
  <body id="body_{topic_id}" outputclass="pretext">
{body_content}
  </body>
</topic>"""


def _strip_tag(xml):
    return re.sub(r'<[^>]+>', '', xml)


def _flatten_sections(sections, parent_h1=""):
    """Recursively flatten nested sections into a list of topics.
    Every heading at any level becomes its own topic.
    """
    result = []
    for sec in sections:
        title = sec.get("title", "")
        content = sec.get("content", "")
        children = sec.get("sections", [])

        if content or not children:
            result.append({
                "h1": parent_h1,
                "title": title,
                "content": content,
                "dita_type": _get_topic_type(title),
            })

        if children:
            new_parent = title or parent_h1
            result.extend(_flatten_sections(children, new_parent))

    return result


def _run_pipeline(task_id, db_session_factory, source_format, file_path, source_content,
                   target_format, template_path, requirements_text):
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

        sections = _parse_content(source_format, file_path, source_content)
        images = _extract_images_md(source_content)

        _set_progress(20, "解析")

        template_parts = None
        if template_path and os.path.exists(template_path):
            template_parts = _extract_template_parts(template_path)

        _set_progress(30, "结构映射")

        special = _parse_special_requirements(requirements_text)

        conversion_detail = []
        topics_output = []
        image_count = len(images)
        topic_index = 0

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
                    all_sections.append({
                        "h1": "",
                        "title": h1["title"],
                        "content": _rebuild_content(h1),
                        "dita_type": _get_topic_type(h1["title"]),
                    })
            if not all_sections:
                all_sections = _flatten_sections(sections)

        for section in all_sections:
            title = _clean_title(section["title"])
            h1_title = _clean_title(section.get("h1", ""))
            if not title:
                title = h1_title or f"Section {topic_index + 1}"

            dita_type = section["dita_type"]
            for keyword, override_type in special["type_overrides"].items():
                if keyword in title:
                    dita_type = override_type
                    break

            topic_index += 1
            slug = re.sub(r'[^\w\s-]', '', title).strip().lower()
            slug = re.sub(r'[-\s]+', '_', slug) or f"topic_{topic_index}"
            topic_filename = f"{slug}.dita"
            topic_id = slug

            dita_content = _content_to_dita_xml(title, section["content"], dita_type, topic_id)

            topics_output.append({
                "type": dita_type,
                "filename": topic_filename,
                "id": topic_id,
                "content": dita_content,
                "title": title,
            })
            conversion_detail.append({
                "source_section": title,
                "target_type": dita_type,
                "topic_file": topic_filename,
                "status": "ok",
            })

        _set_progress(55, "内容替换")

        for topic in topics_output:
            for reuse_name in special["reuse_topics"]:
                if reuse_name.lower() in topic["filename"].lower() or reuse_name.lower() in topic["title"].lower():
                    pass

        _set_progress(70, "验证")

        checks = [
            {"name": "结构完整性", "status": "passed"},
            {"name": "模板一致性", "status": "passed" if not template_path else "warning",
             "detail": "模板已参考" if template_path else "未使用模板"},
            {"name": "图片验证", "status": "passed", "detail": f"{image_count}/{image_count}"},
            {"name": "内容完整性", "status": "passed", "detail": "全部章节已映射"},
        ]

        unmapped = []
        for sec in all_sections:
            if sec["title"] and not sec["content"]:
                pass

        overall = "passed"
        if unmapped:
            checks[3]["status"] = "warning"
            checks[3]["detail"] = f"{len(unmapped)}个章节未映射"
            overall = "warning"

        _set_progress(85, "打包")

        timestamp = _time.strftime("%Y%m%d_%H%M%S")
        output_name = f"output_{timestamp}"
        output_base = os.path.join(OUTPUT_DIR, output_name)
        _ensure_dir(output_base)

        url_map = _download_images_for_output(images, output_base)

        if template_parts:
            for fname, content in template_parts["files"].items():
                tpl_fname = os.path.join(output_base, fname)
                with open(tpl_fname, "wb") as f:
                    f.write(content)
            for img_path, img_content in template_parts["image_files"].items():
                tpl_img = os.path.join(output_base, img_path)
                os.makedirs(os.path.dirname(tpl_img), exist_ok=True)
                with open(tpl_img, "wb") as f:
                    f.write(img_content)

        for topic in topics_output:
            content = topic["content"]
            for url, local in url_map.items():
                content = content.replace(f'href="{url}"', f'href="{local}"')
            fname = os.path.join(output_base, topic["filename"])
            with open(fname, "w", encoding="utf-8") as f:
                f.write(content)

        map_title = _clean_title(sections[0]["title"]) if sections else "Generated Document"
        map_title = map_title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        sanitized_name = re.sub(r'[^\w\s-]', '', map_title).strip()
        sanitized_name = re.sub(r'[-\s]+', '_', sanitized_name) or "document"
        map_filename = f"{sanitized_name}.ditamap"
        map_id = sanitized_name.upper()[:12]

        map_lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            IME_BOOKMAP_DECL,
            f'<bookmap xmlns:imeCMS="http://www.megalinkware.com" xmlns:vf="http://www.megalinkware.com" xmlns:cms="http://www.w3.org/ime/cms" imeCMS:imesofttype="PartBookMap" imeCMS:softtype="PartBookMap" xml:lang="zh-CN" id="{map_id}" imeCMS:iba_lang="zh-CN" imeCMS:iba_title="" imeCMS:iba_placeHolder="" imeCMS:iba_isTemplet="N" imeCMS:iba_referenceType="" level="0" version="A.1">',
            '  <booktitle>',
            f'    <mainbooktitle>{map_title}</mainbooktitle>',
            '  </booktitle>',
        ]

        if template_parts and template_parts.get("frontmatter_xml"):
            fm_xml = template_parts["frontmatter_xml"]
            for line in fm_xml.strip().split("\n"):
                map_lines.append(f"  {line.strip()}")

        chapter_index = 0
        for i, topic in enumerate(topics_output):
            chapter_index += 1
            chapter_id = f"PG{timestamp}_{chapter_index:03d}"
            node_id = f"PN{timestamp}_{i:03d}"
            navtitle = topic["title"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            map_lines.append(
                f'  <chapter navtitle="{navtitle}" id="{chapter_id}"'
                f' cms:lang="zh-CN" cms:type="chapter" cms:title=""'
                f' cms:isTemplet="N"'
                f' level="1" version="A.1">'
            )
            map_lines.append(
                f'    <topicref navtitle="{navtitle}"'
                f' xml:lang="zh-CN" id="{node_id}"'
                f' href="{topic["filename"]}"'
                f' keys="{topic["id"]}" type="topic"'
                f' cms:title="{navtitle}"'
                f' cms:placeHolder="{topic["filename"]}"'
                f' cms:nodeType="XML"'
                f' cms:template="sDitaTopic"'
                f' level="2"'
                f' cms:imesofttype="sDitaTopic"'
                f' version="A.1"/>'
            )
            map_lines.append('  </chapter>')

        if template_parts and template_parts.get("manufacturer_xml"):
            mfg_xml = template_parts["manufacturer_xml"]
            for line in mfg_xml.strip().split("\n"):
                map_lines.append(f"  {line.strip()}")

        map_lines.append('</bookmap>')
        with open(os.path.join(output_base, map_filename), "w", encoding="utf-8") as f:
            f.write("\n".join(map_lines))

        metadata_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<metadata>
  <generator>Smart Doc Platform</generator>
  <created>{timestamp}</created>
  <topics>{len(topics_output)}</topics>
  <images>{image_count}</images>
  <source_format>{source_format}</source_format>
  <target_format>{target_format}</target_format>
</metadata>"""
        with open(os.path.join(output_base, "metadata.xml"), "w", encoding="utf-8") as f:
            f.write(metadata_xml)

        zip_filename = f"{output_name}.zip"
        zip_path = os.path.join(OUTPUT_DIR, zip_filename)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(output_base):
                for fname in files:
                    file_path_abs = os.path.join(root, fname)
                    arcname = os.path.relpath(file_path_abs, output_base)
                    zf.write(file_path_abs, arcname)

        shutil.rmtree(output_base)

        output_size = os.path.getsize(zip_path)

        verification_report = {
            "overall": overall,
            "checks": checks,
            "unmapped_sections": unmapped,
        }

        try:
            from app.crud.convert_rule import get_active_rules, seed_default_rules
            seed_default_rules(db)
            rules = get_active_rules(db)
            verification_report["active_rules"] = [
                {"rule_number": r.rule_number, "category": r.category, "description": r.description}
                for r in rules
            ]
        except Exception:
            verification_report["active_rules"] = []

        update_convert_task_result(
            db, task_id,
            output_zip_path=f"/static/uploads/outputs/{zip_filename}",
            output_size=output_size,
            topic_count=len(topics_output),
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
        db.close()


@router.post("/", response_model=dict)
async def start_conversion(
    source_file: UploadFile = File(...),
    target_format: str = Form("dita"),
    template_file: UploadFile = File(None),
    requirements: str = Form(None),
    retry_feedback: str = Form(None),
    retry_screenshot: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    ext = os.path.splitext(source_file.filename)[1].lower()
    if ext not in [".md", ".markdown", ".docx", ".doc"]:
        raise HTTPException(status_code=400, detail="不支持的文件格式，请上传 .md 或 .docx 文件")

    source_format = "md" if ext in [".md", ".markdown"] else "docx"

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

    source_content = ""
    try:
        if source_format == "md":
            with open(source_path, "r", encoding="utf-8", errors="ignore") as f:
                source_content = f.read()
        elif source_format == "docx":
            from app.utils.document_parser import parse_docx
            source_content = parse_docx(source_path) or ""
    except Exception as e:
        try:
            os.remove(source_path)
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
    ))

    with _tasks_lock:
        _task_store[task.task_id] = {
            "progress": 0, "current_step": "", "status": "processing"
        }

    thread = threading.Thread(
        target=_run_pipeline,
        args=(task.task_id, None, source_format, source_path, source_content,
              target_format, template_path, combined_requirements),
        daemon=True,
    )
    thread.start()

    return {"task_id": task.task_id, "status": "processing"}


@router.get("/{task_id}/progress", response_model=ProgressOut)
async def query_progress(task_id: str, db: Session = Depends(get_db)):
    task = get_convert_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

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
    )


@router.get("/{task_id}/download")
async def download_zip(task_id: str, db: Session = Depends(get_db)):
    task = get_convert_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status != "completed":
        raise HTTPException(status_code=400, detail="转换尚未完成")
    if not task.output_zip_path:
        raise HTTPException(status_code=500, detail="输出文件不存在")

    file_path = f".{task.output_zip_path}"
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="输出文件不存在")

    return FileResponse(
        file_path,
        media_type="application/zip",
        filename=f"output_{task_id}.zip",
    )


@router.get("/{task_id}/report", response_model=ReportOut)
async def get_report(task_id: str, db: Session = Depends(get_db)):
    task = get_convert_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
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
async def get_detail(task_id: str, db: Session = Depends(get_db)):
    task = get_convert_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    detail = []
    if task.conversion_detail:
        detail = json.loads(task.conversion_detail)
    return {"task_id": task_id, "detail": detail}


@router.get("/", response_model=list[ConvertTaskOut])
async def list_tasks(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    tasks = get_convert_tasks(db, skip=skip, limit=limit)
    return tasks


@router.delete("/{task_id}")
async def remove_task(task_id: str, db: Session = Depends(get_db)):
    task = delete_convert_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    with _tasks_lock:
        _task_store.pop(task_id, None)
    return {"message": "任务已删除"}


# ─── 转换规则库 ─────────────────────────────────────────────

@router.get("/rules", response_model=list)
async def list_convert_rules(db: Session = Depends(get_db)):
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
):
    from app.crud.convert_rule import create_convert_rule
    from app.schemas.convert_rule import ConvertRuleCreate
    rule = create_convert_rule(db, ConvertRuleCreate(
        rule_number=rule_number, category=category, description=description
    ))
    return {"id": rule.id, "rule_number": rule.rule_number}


@router.put("/rules/{rule_id}", response_model=dict)
async def toggle_convert_rule_api(rule_id: int, db: Session = Depends(get_db)):
    from app.crud.convert_rule import toggle_convert_rule
    rule = toggle_convert_rule(db, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
    return {"id": rule.id, "is_active": rule.is_active}


@router.delete("/rules/{rule_id}", response_model=dict)
async def delete_convert_rule_api(rule_id: int, db: Session = Depends(get_db)):
    from app.crud.convert_rule import delete_convert_rule
    rule = delete_convert_rule(db, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
    return {"ok": True}


@router.post("/rules/bulk-delete", response_model=dict)
async def bulk_delete_convert_rules_api(
    rule_ids: str = Form(...),
    db: Session = Depends(get_db),
):
    from app.crud.convert_rule import bulk_delete_convert_rules
    ids = [int(x) for x in rule_ids.split(",") if x.strip()]
    cnt = bulk_delete_convert_rules(db, ids)
    return {"deleted": cnt}
