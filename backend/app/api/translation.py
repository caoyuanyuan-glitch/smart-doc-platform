from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
import os
import io
import csv
import json
import zipfile
import tempfile
import sys
import threading
import xml.etree.ElementTree as ET
import lxml.etree as ET_LXML
import re

from app.database import get_db, SessionLocal
from app.schemas.translation import TranslationRequest, TranslationResponse, MemoryEntry, MemoryEntryOut, TranslationDocOut
from app.crud.document import get_document, get_documents
from app.crud.review import get_reviews
from app.crud.memory import (
    create_memory_entry, get_memory_entries, get_memory_entry,
    delete_memory_entry, search_memory, get_memory_banks
)
from app.models.knowledge import KnowledgeFile
from app.models.translation_doc import TranslationDoc
from app.utils.document_parser import parse_file
from app.utils.ai_client import ai_client

router = APIRouter()

UPLOAD_DIR = "./static/uploads/translation"
TRANSLATION_OUTPUT_DIR = "./static/translations"

_translate_tasks = {}
_translate_tasks_lock = threading.Lock()
_thread_locals = threading.local()
_memory_file_cache = {}
_memory_file_cache_lock = threading.Lock()


def _get_memory_bank():
    return getattr(_thread_locals, 'memory_bank', None)


def _set_memory_bank(bank: str):
    _thread_locals.memory_bank = bank if bank else None


def _get_memory_file_id():
    return getattr(_thread_locals, 'memory_file_id', None)


def _set_memory_file_id(file_id):
    _thread_locals.memory_file_id = file_id


def _normalize_header_key(value: str) -> str:
    return re.sub(r"[\s_\-]+", "", str(value or "").strip().lower())


def _parse_memory_text_entries(raw_text: str):
    entries = []
    delimiters = ["\t", "=>", "->", "→", "|", "｜"]
    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        for delimiter in delimiters:
            if delimiter in line:
                source_text, translated_text = [part.strip() for part in line.split(delimiter, 1)]
                if source_text and translated_text:
                    entries.append({
                        "source_text": source_text,
                        "translated_text": translated_text
                    })
                break
    return entries


def _normalize_memory_entry(row: dict):
    if not isinstance(row, dict):
        return None

    normalized_row = {_normalize_header_key(key): value for key, value in row.items()}
    source_keys = ["source", "sourcetext", "src", "原文", "源文", "text"]
    target_keys = ["target", "translatedtext", "translation", "译文", "targettext", "result"]
    source_lang_keys = ["sourcelang", "srclang", "源语言"]
    target_lang_keys = ["targetlang", "tgtlang", "目标语言"]

    def pick_value(keys):
        for key in keys:
            normalized_key = _normalize_header_key(key)
            if normalized_key in normalized_row:
                value = normalized_row[normalized_key]
                if value is not None and str(value).strip() != "":
                    return str(value).strip()
        return None

    source_text = pick_value(source_keys)
    translated_text = pick_value(target_keys)
    if not source_text or not translated_text:
        return None

    return {
        "source_text": source_text,
        "translated_text": translated_text,
        "source_lang": pick_value(source_lang_keys),
        "target_lang": pick_value(target_lang_keys),
    }


def _load_memory_entries_from_json(file_path: str):
    with open(file_path, "r", encoding="utf-8") as handle:
        data = json.load(handle)

    if isinstance(data, dict):
        for key in ["entries", "items", "data", "records"]:
            if isinstance(data.get(key), list):
                data = data[key]
                break

    if not isinstance(data, list):
        return []

    entries = []
    for item in data:
        normalized = _normalize_memory_entry(item)
        if normalized:
            entries.append(normalized)
    return entries


def _load_memory_entries_from_delimited_file(file_path: str, delimiter: str = None):
    with open(file_path, "r", encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(2048)
        handle.seek(0)
        if delimiter is None:
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
                delimiter = dialect.delimiter
            except Exception:
                delimiter = ","
        reader = csv.DictReader(handle, delimiter=delimiter)
        entries = []
        for row in reader:
            normalized = _normalize_memory_entry(row)
            if normalized:
                entries.append(normalized)
        return entries


def _load_memory_entries_from_excel(file_path: str):
    from openpyxl import load_workbook

    workbook = load_workbook(file_path, read_only=True, data_only=True)
    worksheet = workbook.active
    rows = list(worksheet.iter_rows(values_only=True))
    if not rows:
        return []

    headers = [str(cell).strip() if cell is not None else "" for cell in rows[0]]
    entries = []
    for row_values in rows[1:]:
        row = {headers[index]: row_values[index] for index in range(min(len(headers), len(row_values)))}
        normalized = _normalize_memory_entry(row)
        if normalized:
            entries.append(normalized)
    return entries


def _load_memory_file_entries(file_path: str, file_type: str):
    ext = file_type.lower()
    if ext == "json":
        return _load_memory_entries_from_json(file_path)
    if ext in ["csv", "tsv"]:
        return _load_memory_entries_from_delimited_file(file_path, "\t" if ext == "tsv" else None)
    if ext in ["xlsx", "xlsm", "xltx", "xltm"]:
        return _load_memory_entries_from_excel(file_path)

    try:
        raw_text = parse_file(file_path)
    except Exception:
        raw_text = ""
    return _parse_memory_text_entries(raw_text or "")


def _get_cached_memory_file_entries(memory_file: KnowledgeFile):
    cache_key = (
        memory_file.id,
        memory_file.updated_at.isoformat() if memory_file.updated_at else "",
        memory_file.file_path,
    )
    with _memory_file_cache_lock:
        if cache_key in _memory_file_cache:
            return _memory_file_cache[cache_key]

    entries = _load_memory_file_entries(memory_file.file_path, memory_file.file_type or "")
    with _memory_file_cache_lock:
        _memory_file_cache[cache_key] = entries
    return entries


def _search_memory_file(db: Session, memory_file_id: int, source_text: str, source_lang: str, target_lang: str,
                        threshold: float = 0.7):
    if not memory_file_id:
        return None

    memory_file = db.query(KnowledgeFile).filter(KnowledgeFile.id == memory_file_id).first()
    if not memory_file or not os.path.exists(memory_file.file_path):
        return None

    entries = _get_cached_memory_file_entries(memory_file)
    candidates = []
    for entry in entries:
        entry_source_lang = (entry.get("source_lang") or source_lang).strip()
        entry_target_lang = (entry.get("target_lang") or target_lang).strip()
        if entry_source_lang != source_lang or entry_target_lang != target_lang:
            continue
        candidates.append(entry)

    for entry in candidates:
        if entry["source_text"].strip() == source_text.strip():
            return entry["translated_text"]

    best_match = None
    best_score = threshold
    for entry in candidates:
        if len(source_text) <= 20:
            continue
        shorter = min(entry["source_text"], source_text, key=len)
        longer = max(entry["source_text"], source_text, key=len)
        score = sum(1 for char in shorter if char in longer) / len(longer) if longer else 0
        if score > best_score:
            best_score = score
            best_match = entry["translated_text"]

    return best_match


def _do_translate(text: str, engine: str, model: str, source_lang: str, target_lang: str, db: Session) -> str:
    result = None
    if engine in ["memory", "hybrid"]:
        r, hit = translate_with_memory(
            text,
            source_lang,
            target_lang,
            db,
            bank=_get_memory_bank(),
            memory_file_id=_get_memory_file_id(),
        )
        if hit:
            result = r
    if engine in ["ai", "hybrid"] and not result:
        result = translate_with_ai(text, model, source_lang, target_lang)
    if not result:
        raise HTTPException(status_code=500, detail="翻译失败")
    return result


def _translate_dita_xml(fpath: str, engine: str, model: str, source_lang: str, target_lang: str, db: Session) -> tuple:
    """Returns (translated_content, all_original_parts, all_translated_parts)"""
    all_original_parts = []
    all_translated_parts = []

    with open(fpath, "rb") as f:
        raw_bytes = f.read()
    raw_str = raw_bytes.decode("utf-8")

    ns_decls = re.findall(r'xmlns:(\w+)="([^"]*)"', raw_str)
    for prefix, uri in ns_decls:
        if prefix:
            ET_LXML.register_namespace(prefix, uri)

    parser = ET_LXML.XMLParser(remove_blank_text=False, strip_cdata=False)
    tree = ET_LXML.parse(fpath, parser)
    root = tree.getroot()

    def _translate_element(elem):
        if elem.text and elem.text.strip():
            orig = elem.text
            stripped = orig.strip()
            translated = _do_translate(stripped, engine, model, source_lang, target_lang, db)
            elem.text = orig.replace(stripped, translated, 1)
            all_original_parts.append(stripped)
            all_translated_parts.append(translated)
        for child in elem:
            _translate_element(child)
        if elem.tail and elem.tail.strip():
            orig = elem.tail
            stripped = orig.strip()
            translated = _do_translate(stripped, engine, model, source_lang, target_lang, db)
            elem.tail = orig.replace(stripped, translated, 1)
            all_original_parts.append(stripped)
            all_translated_parts.append(translated)

    _translate_element(root)

    doctype = tree.docinfo.doctype
    result_bytes = ET_LXML.tostring(
        tree,
        xml_declaration=True,
        encoding="UTF-8",
        doctype=doctype,
        pretty_print=False,
    )
    return result_bytes.decode("utf-8"), all_original_parts, all_translated_parts


def _translate_xlf_xml(fpath: str, engine: str, model: str, source_lang: str, target_lang: str, db: Session) -> tuple:
    all_original_parts = []
    all_translated_parts = []

    tree = ET.parse(fpath)
    root_xliff = tree.getroot()
    xliff_ns = "urn:oasis:names:tc:xliff:document:1.2"
    ET.register_namespace("", xliff_ns)

    for trans_unit in root_xliff.iter(f"{{{xliff_ns}}}trans-unit"):
        source_el = trans_unit.find(f"{{{xliff_ns}}}source")
        if source_el is None:
            continue

        target_parts = []
        text_segments = []

        if source_el.text and source_el.text.strip():
            seg = source_el.text.strip()
            text_segments.append(seg)
            target_parts.append(_do_translate(seg, engine, model, source_lang, target_lang, db))

        for child in list(source_el):
            child_tail = child.tail
            child.tail = None
            tag_str = ET.tostring(child, encoding="unicode").strip()
            child.tail = child_tail
            target_parts.append(tag_str)
            if child_tail and child_tail.strip():
                seg = child_tail.strip()
                text_segments.append(seg)
                target_parts.append(_do_translate(seg, engine, model, source_lang, target_lang, db))

        if not target_parts:
            continue

        target_content = "".join(target_parts)
        target_el = trans_unit.find(f"{{{xliff_ns}}}target")
        target_str = f"<target>{target_content}</target>"
        try:
            target_fragment = ET.fromstring(target_str)
        except Exception:
            continue
        if target_el is not None:
            trans_unit.remove(target_el)
        trans_unit.append(target_fragment)
        target_fragment.set("state", "translated")

        all_original_parts.append(" ".join(text_segments))
        all_translated_parts.append(target_content)

    return ET.tostring(root_xliff, encoding="unicode"), all_original_parts, all_translated_parts


def _translate_pptx_xml(fpath: str, engine: str, model: str, source_lang: str, target_lang: str, db: Session) -> tuple:
    """Returns (translated_bytes, all_original_parts, all_translated_parts)"""
    PPTX_NS = {
        "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
        "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    }
    DRAWING_NS = PPTX_NS["a"]

    for prefix, uri in PPTX_NS.items():
        ET_LXML.register_namespace(prefix, uri)

    in_buf = io.BytesIO()
    with open(fpath, "rb") as f:
        in_buf.write(f.read())
    in_buf.seek(0)

    pptx_original = []
    pptx_translated = []
    texts_to_translate = []
    xml_roots = {}
    text_targets = []

    with zipfile.ZipFile(in_buf, 'r') as z_in:
        for zinfo in z_in.infolist():
            name = zinfo.filename
            if not name.endswith(".xml") or "/_rels/" in name:
                continue
            if not (name.startswith("ppt/slides/slide") or name.startswith("ppt/notesSlides/notesSlide")):
                continue

            raw = z_in.read(zinfo)
            root = ET_LXML.fromstring(raw if isinstance(raw, bytes) else raw.encode("utf-8"))
            xml_roots[name] = root
            for t_elem in root.iter(f"{{{DRAWING_NS}}}t"):
                if t_elem.text and t_elem.text.strip():
                    texts_to_translate.append(t_elem.text.strip())
                    text_targets.append(t_elem)

    if texts_to_translate:
        sep = "\n---PPTXSEG---\n"
        combined = sep.join(texts_to_translate)
        translated_combined = _do_translate(combined, engine, model, source_lang, target_lang, db)
        translated_parts = [p.strip() for p in translated_combined.split(sep)]
        if len(translated_parts) != len(texts_to_translate):
            translated_parts = [_do_translate(t, engine, model, source_lang, target_lang, db) for t in texts_to_translate]
        for i, t_elem in enumerate(text_targets):
            if i < len(translated_parts):
                translated = translated_parts[i]
                pptx_original.append(texts_to_translate[i])
                pptx_translated.append(translated)
                t_elem.text = translated

    out_buf = io.BytesIO()
    in_buf.seek(0)
    with zipfile.ZipFile(in_buf, 'r') as z_in:
        with zipfile.ZipFile(out_buf, 'w', zipfile.ZIP_DEFLATED) as z_out:
            for zinfo in z_in.infolist():
                raw = z_in.read(zinfo)
                name = zinfo.filename
                if name in xml_roots:
                    raw = ET_LXML.tostring(xml_roots[name], xml_declaration=True, encoding="UTF-8", pretty_print=False)
                z_out.writestr(zinfo, raw)
    out_buf.seek(0)

    return out_buf.read(), pptx_original, pptx_translated


def _translate_docx(fpath: str, engine: str, model: str, source_lang: str, target_lang: str, db: Session) -> tuple:
    """Translate DOCX preserving formatting (paragraphs, runs, tables, headers, footers)."""
    from docx import Document

    doc = Document(fpath)
    all_original = []
    all_translated = []

    paragraphs_to_translate = []

    for para in doc.paragraphs:
        full_text = para.text
        if full_text.strip():
            paragraphs_to_translate.append(para)

    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    full_text = para.text
                    if full_text.strip():
                        paragraphs_to_translate.append(para)

    texts = [p.text for p in paragraphs_to_translate]
    if texts:
        sep = "\n---DOCXPARA---\n"
        combined = sep.join(texts)
        translated_combined = _do_translate(combined, engine, model, source_lang, target_lang, db)
        translated_texts = [t.strip() for t in translated_combined.split(sep)]
        if len(translated_texts) != len(texts):
            translated_texts = [_do_translate(t, engine, model, source_lang, target_lang, db) for t in texts]
        for i, para in enumerate(paragraphs_to_translate):
            if i < len(translated_texts):
                translated = translated_texts[i]
                all_original.append(texts[i])
                all_translated.append(translated)
                runs = para.runs
                if not runs:
                    continue
                if len(runs) == 1:
                    runs[0].text = translated
                else:
                    total_orig = sum(len(r.text or "") for r in runs)
                    if total_orig == 0:
                        runs[0].text = translated
                        for r in runs[1:]:
                            r.text = ""
                    else:
                        pos = 0
                        for r in runs:
                            orig_len = len(r.text or "")
                            chunk_len = max(1, int(len(translated) * orig_len / total_orig))
                            chunk = translated[pos:pos + chunk_len]
                            r.text = chunk
                            pos += chunk_len
                        if pos < len(translated):
                            runs[-1].text += translated[pos:]

    out_buf = io.BytesIO()
    doc.save(out_buf)
    out_buf.seek(0)
    return out_buf.read(), all_original, all_translated


def _translate_xlsx(fpath: str, engine: str, model: str, source_lang: str, target_lang: str, db: Session) -> tuple:
    """Translate XLSX preserving all formatting, formulas, and structure."""
    from openpyxl import load_workbook

    wb = load_workbook(fpath)
    all_original = []
    all_translated = []
    cells_to_translate = []

    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if cell.value and isinstance(cell.value, str) and cell.value.strip():
                    cells_to_translate.append(cell)

    texts = [c.value.strip() for c in cells_to_translate]
    if texts:
        sep = "\n---XLSXCELL---\n"
        combined = sep.join(texts)
        translated_combined = _do_translate(combined, engine, model, source_lang, target_lang, db)
        translated_texts = [t.strip() for t in translated_combined.split(sep)]
        if len(translated_texts) != len(texts):
            translated_texts = [_do_translate(t, engine, model, source_lang, target_lang, db) for t in texts]
        for i, cell in enumerate(cells_to_translate):
            if i < len(translated_texts):
                all_original.append(texts[i])
                all_translated.append(translated_texts[i])
                cell.value = translated_texts[i]

    out_buf = io.BytesIO()
    wb.save(out_buf)
    out_buf.seek(0)
    return out_buf.read(), all_original, all_translated


def _translate_pdf(fpath: str, engine: str, model: str, source_lang: str, target_lang: str, db: Session) -> tuple:
    """Translate PDF: extracts text page-by-page, translates, outputs structured text (PDF font limitation)."""
    import pdfplumber

    all_original = []
    all_translated = []
    pages_text = []

    with pdfplumber.open(fpath) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            pages_text.append(text.strip() if text and text.strip() else "")

    non_empty = [p for p in pages_text if p]
    if non_empty:
        sep = "\n---PDFPAGE---\n"
        combined = sep.join(non_empty)
        translated_combined = _do_translate(combined, engine, model, source_lang, target_lang, db)
        translated_pages = translated_combined.split(sep)
    else:
        translated_pages = []

    all_original = non_empty
    all_translated = translated_pages

    output_lines = []
    ti = 0
    for pi, page_text in enumerate(pages_text):
        if page_text:
            output_lines.append(f"=== Page {pi + 1} ===")
            if ti < len(translated_pages):
                output_lines.append(translated_pages[ti])
                ti += 1
            output_lines.append("")
        else:
            output_lines.append(f"=== Page {pi + 1} === [no text]")
            output_lines.append("")

    output_text = "\n".join(output_lines)
    return output_text.encode("utf-8"), all_original, all_translated


def _translate_markdown(fpath: str, engine: str, model: str, source_lang: str, target_lang: str, db: Session) -> tuple:
    """Translate Markdown preserving all syntax (headings, links, code blocks, tables, lists)."""
    import re as md_re

    with open(fpath, "r", encoding="utf-8") as f:
        content = f.read()

    code_blocks = []
    inline_codes = []
    links = []
    images = []

    def _preserve_code_blocks(text):
        def _repl(m):
            code_blocks.append(m.group(0))
            return f"%%CODEBLOCK{len(code_blocks) - 1}%%"
        return md_re.sub(r'```[\s\S]*?```', _repl, text)

    def _preserve_inline_code(text):
        def _repl(m):
            inline_codes.append(m.group(0))
            return f"%%INLINECODE{len(inline_codes) - 1}%%"
        return md_re.sub(r'`[^`]+`', _repl, text)

    def _preserve_links(text):
        def _repl(m):
            links.append(m.group(0))
            return f"%%LINK{len(links) - 1}%%"
        return md_re.sub(r'\[([^\]]*)\]\([^)]+\)', _repl, text)

    def _preserve_images(text):
        def _repl(m):
            images.append(m.group(0))
            return f"%%IMAGE{len(images) - 1}%%"
        return md_re.sub(r'!\[([^\]]*)\]\([^)]+\)', _repl, text)

    protected = content
    protected = _preserve_code_blocks(protected)
    protected = _preserve_inline_code(protected)
    protected = _preserve_images(protected)
    protected = _preserve_links(protected)

    translated = _do_translate(protected, engine, model, source_lang, target_lang, db)

    for i, cb in enumerate(code_blocks):
        translated = translated.replace(f"%%CODEBLOCK{i}%%", cb)
    for i, ic in enumerate(inline_codes):
        translated = translated.replace(f"%%INLINECODE{i}%%", ic)
    for i, img in enumerate(images):
        translated = translated.replace(f"%%IMAGE{i}%%", img)
    for i, link in enumerate(links):
        translated = translated.replace(f"%%LINK{i}%%", link)

    return translated.encode("utf-8"), [content], [translated]


def translate_with_ai(content: str, model: str, source_lang: str, target_lang: str) -> str:
    lang_names = {
        "zh": "中文", "en": "英文", "ja": "日文", "ko": "韩文",
        "fr": "法文", "de": "德文", "es": "西班牙文", "ru": "俄文"
    }
    src_name = lang_names.get(source_lang, source_lang)
    tgt_name = lang_names.get(target_lang, target_lang)

    prompt = f"""你是一个专业的技术文档翻译引擎。请将以下{src_name}文本翻译为{tgt_name}。

翻译规则：
1. 必须严格将原文内容翻译为{tgt_name}，输出必须是纯{tgt_name}文本，不得包含{src_name}
2. 保持原文的段落结构、编号、列表格式完全不变
3. 使用专业准确的技术术语
4. 只输出翻译后的{tgt_name}结果，不要添加任何解释、注释或原始文本

原文：
{content[:8000]}"""
    messages = [{"role": "user", "content": prompt}]

    if model == "kimi":
        result = ai_client.call_kimi(messages, max_tokens=4096)
        if result is None:
            result = ai_client.chat(messages, max_tokens=4096, fallback=True)
    elif model == "deepseek":
        result = ai_client.call_deepseek(messages, max_tokens=4096)
        if result is None:
            result = ai_client.chat(messages, max_tokens=4096, fallback=True)
    elif model == "qwen":
        result = ai_client.call_qwen(messages, max_tokens=4096)
        if result is None:
            result = ai_client.chat(messages, max_tokens=4096, fallback=True)
    else:
        result = ai_client.chat(messages, max_tokens=4096, fallback=True)

    if result is None:
        raise HTTPException(
            status_code=500,
            detail="AI翻译引擎不可用，请检查 QWEN (DASHSCOPE_API_KEY)、DeepSeek (DEEPSEEK_API_KEY) 或 Kimi (KIMI_API_KEY) 的 API Key 是否已配置"
        )

    return result


def translate_with_memory(content: str, source_lang: str, target_lang: str,
                          db: Session, bank: str = None, memory_file_id: int = None) -> tuple:
    file_result = _search_memory_file(db, memory_file_id, content, source_lang, target_lang)
    if file_result:
        return file_result, True
    memory_result = search_memory(db, content, source_lang, target_lang, bank=bank)
    if memory_result:
        return memory_result, True
    return None, False


def _translate_filename(filename: str, source_lang: str, target_lang: str) -> str:
    if source_lang == target_lang:
        return filename

    lang_names = {
        "zh": "Chinese", "en": "English", "ja": "Japanese", "ko": "Korean",
        "fr": "French", "de": "German", "es": "Spanish", "ru": "Russian"
    }
    src_name = lang_names.get(source_lang, source_lang)
    tgt_name = lang_names.get(target_lang, target_lang)

    prompt = f'Translate this filename from {src_name} to {tgt_name}. Output ONLY the translated filename, no other text: "{filename}"'
    messages = [{"role": "user", "content": prompt}]
    result = ai_client._call_model(messages, max_tokens=500)

    if result:
        translated = result.strip().strip('"').strip("'").replace("/", "_").replace("\\", "_").replace(":", "_")
        if translated and translated != filename:
            return translated

    return filename


def _run_translate_thread(doc_id: int, file_path: str, ext: str, filename: str,
                          engine: str, model: str, source_lang: str, target_lang: str,
                          memory_bank: str = "", memory_file_id: int = None):
    """Background thread that performs the actual translation and updates the DB record."""
    db = SessionLocal()
    _set_memory_bank(memory_bank)
    _set_memory_file_id(memory_file_id)
    try:
        with _translate_tasks_lock:
            _translate_tasks[doc_id] = {"status": "processing", "error": None}

        if not os.path.exists(TRANSLATION_OUTPUT_DIR):
            os.makedirs(TRANSLATION_OUTPUT_DIR, exist_ok=True)

        base_name = os.path.splitext(filename)[0]
        translated_filename = _translate_filename(base_name, source_lang, target_lang)
        output_filename = f"{translated_filename}{ext}"
        output_path = os.path.join(TRANSLATION_OUTPUT_DIR, output_filename)

        all_original_parts = []
        all_translated_parts = []

        if ext == ".zip":
            with tempfile.TemporaryDirectory() as tmpdir:
                translated_files = []
                with zipfile.ZipFile(file_path, 'r') as zf:
                    for zinfo in zf.infolist():
                        if zinfo.is_dir():
                            continue
                        zip_name = zinfo.filename
                        safe_fname = f"_tmp_{len(translated_files)}{os.path.splitext(zip_name)[1]}"
                        safe_fpath = os.path.join(tmpdir, safe_fname)
                        try:
                            with open(safe_fpath, "wb") as sf:
                                sf.write(zf.read(zinfo))
                        except Exception:
                            continue
                        _, name_ext = os.path.splitext(zip_name)
                        ext_lower = name_ext.lower()
                        if ext_lower == ".dita":
                            try:
                                translated_content, orig, trans = _translate_dita_xml(safe_fpath, engine, model, source_lang, target_lang, db)
                                all_original_parts.extend(orig)
                                all_translated_parts.extend(trans)
                            except Exception:
                                continue
                        elif ext_lower == ".xlf":
                            try:
                                translated_content, orig, trans = _translate_xlf_xml(safe_fpath, engine, model, source_lang, target_lang, db)
                                all_original_parts.extend(orig)
                                all_translated_parts.extend(trans)
                            except Exception:
                                continue
                        elif ext_lower == ".pptx":
                            try:
                                translated_content, orig, trans = _translate_pptx_xml(safe_fpath, engine, model, source_lang, target_lang, db)
                                all_original_parts.append("\n".join(orig))
                                all_translated_parts.append("\n".join(trans))
                            except Exception:
                                continue
                        elif ext_lower in (".docx", ".doc"):
                            try:
                                translated_content, orig, trans = _translate_docx(safe_fpath, engine, model, source_lang, target_lang, db)
                                all_original_parts.extend(orig)
                                all_translated_parts.extend(trans)
                            except Exception:
                                continue
                        elif ext_lower in (".xlsx", ".xls"):
                            try:
                                translated_content, orig, trans = _translate_xlsx(safe_fpath, engine, model, source_lang, target_lang, db)
                                all_original_parts.extend(orig)
                                all_translated_parts.extend(trans)
                            except Exception:
                                continue
                        elif ext_lower == ".md":
                            try:
                                translated_content, orig, trans = _translate_markdown(safe_fpath, engine, model, source_lang, target_lang, db)
                                all_original_parts.extend(orig)
                                all_translated_parts.extend(trans)
                            except Exception:
                                continue
                        elif ext_lower == ".pdf":
                            try:
                                translated_content, orig, trans = _translate_pdf(safe_fpath, engine, model, source_lang, target_lang, db)
                                all_original_parts.extend(orig)
                                all_translated_parts.extend(trans)
                                name_ext = ".txt"  # PDF outputs structured text
                            except Exception:
                                continue
                        else:
                            try:
                                file_content = parse_file(safe_fpath)
                                if not file_content.strip():
                                    continue
                            except Exception:
                                continue
                            translated_content = _do_translate(file_content, engine, model, source_lang, target_lang, db)
                            all_original_parts.append(file_content)
                            all_translated_parts.append(translated_content)
                        dir_part, name_part = os.path.split(zip_name)
                        name_base = os.path.splitext(name_part)[0]
                        new_name = _translate_filename(name_base, source_lang, target_lang)
                        new_rel = os.path.join(dir_part, f"{new_name}{name_ext}") if dir_part else f"{new_name}{name_ext}"
                        translated_files.append((new_rel, translated_content))
                        if os.path.exists(safe_fpath):
                            os.remove(safe_fpath)
                if not translated_files:
                    raise Exception("ZIP包中未找到可翻译的文件")
                with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as out_zf:
                    for rel_path, content in translated_files:
                        if isinstance(content, bytes):
                            out_zf.writestr(rel_path, content)
                        else:
                            out_zf.writestr(rel_path, content.encode("utf-8"))
        elif ext == ".dita":
            translated_xml, orig, trans = _translate_dita_xml(file_path, engine, model, source_lang, target_lang, db)
            all_original_parts.extend(orig)
            all_translated_parts.extend(trans)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(translated_xml)
        elif ext == ".xlf":
            translated_xml, orig, trans = _translate_xlf_xml(file_path, engine, model, source_lang, target_lang, db)
            all_original_parts.extend(orig)
            all_translated_parts.extend(trans)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(translated_xml)
        elif ext == ".pptx":
            translated_bytes, orig, trans = _translate_pptx_xml(file_path, engine, model, source_lang, target_lang, db)
            all_original_parts.append("\n".join(orig))
            all_translated_parts.append("\n".join(trans))
            with open(output_path, "wb") as f:
                f.write(translated_bytes)
        elif ext in (".docx", ".doc"):
            translated_bytes, orig, trans = _translate_docx(file_path, engine, model, source_lang, target_lang, db)
            all_original_parts.extend(orig)
            all_translated_parts.extend(trans)
            with open(output_path, "wb") as f:
                f.write(translated_bytes)
        elif ext in (".xlsx", ".xls"):
            translated_bytes, orig, trans = _translate_xlsx(file_path, engine, model, source_lang, target_lang, db)
            all_original_parts.extend(orig)
            all_translated_parts.extend(trans)
            with open(output_path, "wb") as f:
                f.write(translated_bytes)
        elif ext == ".md":
            translated_bytes, orig, trans = _translate_markdown(file_path, engine, model, source_lang, target_lang, db)
            all_original_parts.extend(orig)
            all_translated_parts.extend(trans)
            with open(output_path, "wb") as f:
                f.write(translated_bytes)
        elif ext == ".pdf":
            translated_bytes, orig, trans = _translate_pdf(file_path, engine, model, source_lang, target_lang, db)
            all_original_parts.extend(orig)
            all_translated_parts.extend(trans)
            output_filename = f"{translated_filename}.txt"
            output_path = os.path.join(TRANSLATION_OUTPUT_DIR, output_filename)
            with open(output_path, "wb") as f:
                f.write(translated_bytes)
        elif ext == ".txt":
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            if not content.strip():
                raise Exception("无法从文件中提取文本内容")
            translated = _do_translate(content, engine, model, source_lang, target_lang, db)
            all_original_parts.append(content)
            all_translated_parts.append(translated)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(translated)
        else:
            content = parse_file(file_path)
            if not content.strip():
                raise Exception("无法从文件中提取文本内容")
            translated = _do_translate(content, engine, model, source_lang, target_lang, db)
            all_original_parts.append(content)
            all_translated_parts.append(translated)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(translated)

        original_content = "\n\n".join(all_original_parts)
        translated_content = "\n\n".join(all_translated_parts)

        doc = db.query(TranslationDoc).filter(TranslationDoc.id == doc_id).first()
        if doc:
            doc.translated_filename = output_filename
            doc.original_content = original_content[:8000]
            doc.translated_content = translated_content[:8000]
            doc.original_preview = original_content[:500] + "..." if len(original_content) > 500 else original_content
            doc.translated_preview = translated_content[:500] + "..." if len(translated_content) > 500 else translated_content
            db.commit()

        with _translate_tasks_lock:
            _translate_tasks[doc_id] = {"status": "completed", "error": None, "translated_filename": output_filename}

    except Exception as e:
        error_msg = str(e)
        doc = db.query(TranslationDoc).filter(TranslationDoc.id == doc_id).first()
        if doc:
            doc.translated_filename = f"ERROR:{error_msg[:200]}"
            db.commit()
        with _translate_tasks_lock:
            _translate_tasks[doc_id] = {"status": "error", "error": error_msg}
    finally:
        db.close()


@router.post("/translate", response_model=TranslationResponse)
async def translate_text(req: TranslationRequest, db: Session = Depends(get_db)):
    translated = None
    from_memory = False
    from_ai = False
    engine = req.engine
    _set_memory_bank(req.memory_bank)
    _set_memory_file_id(req.memory_file_id)

    if engine in ["memory", "hybrid"]:
        result, hit = translate_with_memory(
            req.content,
            req.source_lang,
            req.target_lang,
            db,
            bank=req.memory_bank,
            memory_file_id=req.memory_file_id,
        )
        if hit:
            translated = result
            from_memory = True
            if engine == "memory":
                return TranslationResponse(
                    original=req.content,
                    translated=translated,
                    engine_used="memory",
                    from_memory=True,
                    from_ai=False
                )

    if engine in ["ai", "hybrid"] and not translated:
        translated = translate_with_ai(req.content, req.model, req.source_lang, req.target_lang)
        from_ai = True

        if engine == "hybrid":
            create_memory_entry(
                db=db,
                source_text=req.content,
                translated_text=translated,
                source_lang=req.source_lang,
                target_lang=req.target_lang,
                tags=req.memory_bank or ""
            )

    if not translated:
        raise HTTPException(status_code=500, detail="翻译失败，AI和记忆库引擎均未返回结果")

    return TranslationResponse(
        original=req.content,
        translated=translated,
        engine_used=engine,
        from_memory=from_memory,
        from_ai=from_ai
    )


@router.post("/translate/file")
async def translate_file(
    file: UploadFile = File(...),
    engine: str = Form("hybrid"),
    model: str = Form("qwen"),
    source_lang: str = Form("zh"),
    target_lang: str = Form("en"),
    memory_bank: str = Form(""),
    memory_file_id: int = Form(None),
    db: Session = Depends(get_db)
):
    if not os.path.exists(UPLOAD_DIR):
        os.makedirs(UPLOAD_DIR, exist_ok=True)

    filename = file.filename
    file_path = os.path.join(UPLOAD_DIR, filename)

    try:
        with open(file_path, "wb") as buffer:
            while chunk := await file.read(1024 * 1024):
                buffer.write(chunk)
    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=500, detail=f"文件保存失败: {str(e)}")

    ext = os.path.splitext(filename)[1].lower()

    doc = TranslationDoc(
        filename=filename,
        file_type=ext.replace(".", ""),
        source_lang=source_lang,
        target_lang=target_lang,
        engine=engine,
        model=model if engine != "memory" else "memory",
        original_content="",
        translated_content="",
        translated_filename="",
        original_preview="",
        translated_preview=""
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    thread = threading.Thread(
        target=_run_translate_thread,
        args=(doc.id, file_path, ext, filename, engine, model, source_lang, target_lang, memory_bank, memory_file_id),
        daemon=True
    )
    thread.start()

    return {
        "message": "翻译任务已提交",
        "doc_id": doc.id,
        "original_filename": filename,
        "download_url": f"/api/translation/download/{doc.id}"
    }


@router.get("/translate/file/{doc_id}/status")
async def get_translate_file_status(doc_id: int, db: Session = Depends(get_db)):
    doc = db.query(TranslationDoc).filter(TranslationDoc.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    orig_filename = doc.filename or ""

    with _translate_tasks_lock:
        task = _translate_tasks.get(doc_id)

    if task:
        return {
            "doc_id": doc_id,
            "status": task["status"],
            "error": task.get("error"),
            "translated_filename": task.get("translated_filename", ""),
            "original_filename": orig_filename,
            "download_url": f"/api/translation/download/{doc_id}" if task["status"] == "completed" else None,
        }

    fn = doc.translated_filename or ""
    if fn == "":
        return {"doc_id": doc_id, "status": "processing", "error": None, "original_filename": orig_filename}
    if fn.startswith("ERROR:"):
        return {"doc_id": doc_id, "status": "error", "error": fn[6:], "original_filename": orig_filename}

    return {
        "doc_id": doc_id,
        "status": "completed",
        "translated_filename": fn,
        "original_filename": orig_filename,
        "download_url": f"/api/translation/download/{doc_id}",
        "error": None
    }


@router.get("/download/{doc_id}")
async def download_translated_file(doc_id: int, db: Session = Depends(get_db)):
    doc = db.query(TranslationDoc).filter(TranslationDoc.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Translation doc not found")

    output_filename = doc.translated_filename
    if not output_filename or output_filename.startswith("ERROR:"):
        raise HTTPException(status_code=404, detail="翻译尚未完成或失败")

    output_path = os.path.join(TRANSLATION_OUTPUT_DIR, output_filename)

    if os.path.exists(output_path):
        media_type = "application/octet-stream"
        if output_filename.endswith(".zip"):
            media_type = "application/zip"
        elif output_filename.endswith(".xlf"):
            media_type = "application/xliff+xml"
        return FileResponse(
            path=output_path,
            filename=output_filename,
            media_type=media_type
        )

    raise HTTPException(status_code=404, detail="文件不存在")


@router.get("/reviewed-docs")
async def get_reviewed_documents(db: Session = Depends(get_db)):
    reviews = get_reviews(db)
    reviewed_doc_ids = set()
    for review in reviews:
        if review.status == "completed":
            reviewed_doc_ids.add(review.document_id)

    documents = get_documents(db, limit=500)
    result = []
    for doc in documents:
        if doc.id in reviewed_doc_ids:
            result.append({
                "id": doc.id,
                "filename": doc.filename,
                "file_type": doc.file_type,
                "preview": doc.preview,
                "created_at": doc.created_at.isoformat() if doc.created_at else None
            })

    return result


@router.get("/memory/banks")
async def get_banks(db: Session = Depends(get_db)):
    """Return list of distinct memory bank names (tags) available for translation."""
    banks = get_memory_banks(db)
    return {"banks": banks}


@router.get("/memory", response_model=list[MemoryEntryOut])
async def list_memory_entries(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=500),
    keyword: str = Query(None),
    db: Session = Depends(get_db)
):
    return get_memory_entries(db, skip=skip, limit=limit, keyword=keyword)


@router.post("/memory", response_model=MemoryEntryOut)
async def add_memory_entry(entry: MemoryEntry, db: Session = Depends(get_db)):
    return create_memory_entry(
        db=db,
        source_text=entry.source_text,
        translated_text=entry.translated_text,
        source_lang=entry.source_lang,
        target_lang=entry.target_lang,
        tags=entry.tags
    )


@router.delete("/memory/{entry_id}")
async def remove_memory_entry(entry_id: int, db: Session = Depends(get_db)):
    entry = delete_memory_entry(db, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Memory entry not found")
    return {"message": "Memory entry deleted successfully"}


@router.get("/docs", response_model=list[TranslationDocOut])
async def list_translation_docs(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db)
):
    docs = db.query(TranslationDoc).order_by(TranslationDoc.created_at.desc()).offset(skip).limit(limit).all()
    return docs


@router.get("/docs/{doc_id}", response_model=TranslationDocOut)
async def get_translation_doc(doc_id: int, db: Session = Depends(get_db)):
    doc = db.query(TranslationDoc).filter(TranslationDoc.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Translation doc not found")
    return doc


@router.delete("/docs/{doc_id}")
async def delete_translation_doc(doc_id: int, db: Session = Depends(get_db)):
    doc = db.query(TranslationDoc).filter(TranslationDoc.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Translation doc not found")
    db.delete(doc)
    db.commit()
    return {"message": "Translation doc deleted successfully"}
