from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse
from sqlalchemy.orm import Session
import html as html_lib
import json
import re
import asyncio
import os
import shutil
import difflib
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from app.database import get_db
from app.crud.document import get_document
from app.crud.review import create_review, get_review, get_reviews, update_review_status, create_issue, get_issues, update_issue
from app.crud.rule import get_rules
from app.crud.term import get_terms
from app.crud.audit_basis import get_audit_basis
from app.crud.knowledge import get_folder_tree, get_folder, get_folder_files
from app.schemas.review import Review, Issue, IssueUpdate, ReviewCreate, IssueCreate
from app.utils.ai_client import ai_client
from app.utils.spell_checker import run_spelling_and_grammar_check
from app.utils.document_parser import clean_pdf_text

_review_progress = {}  # 全局进度存储: {review_id: {'status': 'running', 'step': 'xxx', 'progress': 0-100, 'message': 'xxx'}}
UPLOAD_DIR = Path(__file__).resolve().parents[2] / "static" / "uploads"
REVIEW_EXPORT_DIR = Path(__file__).resolve().parents[2] / "static" / "review_exports"


def get_progress(review_id: int):
    return _review_progress.get(review_id, {'status': 'unknown', 'step': '', 'progress': 0, 'message': ''})


def set_progress(review_id: int, status: str, step: str, progress: int, message: str = ''):
    _review_progress[review_id] = {
        'status': status,
        'step': step,
        'progress': progress,
        'message': message,
        'timestamp': datetime.now().isoformat()
    }

router = APIRouter()


def _issue_value(issue, key, default=''):
    if isinstance(issue, dict):
        return issue.get(key, default)
    return getattr(issue, key, default)


def _normalize_search_text(text):
    return re.sub(r"\s+", "", str(text or "")).lower()


def _encode_issue_position(start=0, end=0, paragraph_index=None, char_start=None, char_end=None):
    payload = {"start": int(start or 0), "end": int(end or 0)}
    if paragraph_index is not None:
        payload["paragraph_index"] = int(paragraph_index)
    if char_start is not None:
        payload["char_start"] = int(char_start)
    if char_end is not None:
        payload["char_end"] = int(char_end)
    return json.dumps(payload, ensure_ascii=False)


def _decode_issue_position(position):
    if not position:
        return {}
    if isinstance(position, dict):
        return position
    text = str(position).strip()
    if text.startswith('{'):
        try:
            data = json.loads(text)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    match = re.match(r"(\d+)-(\d+)", text)
    if match:
        return {"start": int(match.group(1)), "end": int(match.group(2))}
    return {}


def _parse_issue_position(position):
    data = _decode_issue_position(position)
    return (int(data.get("start", 0) or 0), int(data.get("end", 0) or 0))


def _issue_sort_key(issue):
    severity_rank = {"fatal": 4, "serious": 3, "general": 2, "suggestion": 1}
    pos_start, _ = _parse_issue_position(_issue_value(issue, "position", ""))
    return (-severity_rank.get(_issue_value(issue, "severity", "general"), 0), pos_start, _issue_value(issue, "id", 0))


def _iter_docx_paragraphs(doc):
    for para in doc.paragraphs:
        yield para

    def walk_tables(tables):
        for table in tables:
            for row in table.rows:
                for cell in row.cells:
                    for para in cell.paragraphs:
                        yield para
                    yield from walk_tables(cell.tables)

    yield from walk_tables(doc.tables)


def _split_docx_run(run_element, offset):
    w_ns = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    text_elem = run_element.find(f'{{{w_ns}}}t')
    text = text_elem.text if text_elem is not None and text_elem.text is not None else ''
    if offset <= 0 or offset >= len(text):
        return run_element

    right_run = deepcopy(run_element)
    right_text = right_run.find(f'{{{w_ns}}}t')
    if text_elem is None or right_text is None:
        return run_element

    text_elem.text = text[:offset]
    right_text.text = text[offset:]
    parent = run_element.getparent()
    parent.insert(parent.index(run_element) + 1, right_run)
    return right_run


def _collect_docx_text_runs(paragraph):
    w_ns = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    p_element = paragraph._p
    parts = []
    cursor = 0
    for child in p_element:
        tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
        if tag != 'r':
            continue
        text_elem = child.find(f'{{{w_ns}}}t')
        text = text_elem.text if text_elem is not None and text_elem.text else ''
        if not text:
            continue
        start = cursor
        end = cursor + len(text)
        parts.append((child, start, end, text))
        cursor = end
    return parts


def _locate_docx_issue(paragraphs, issue):
    original_text = str(_issue_value(issue, 'original_text', '') or '')
    if not original_text:
        return None, None, None, None

    position_data = _decode_issue_position(_issue_value(issue, 'position', ''))
    paragraph_index = position_data.get('paragraph_index')
    char_start = position_data.get('char_start')
    char_end = position_data.get('char_end')
    if paragraph_index is not None and char_start is not None and char_end is not None:
        if 0 <= int(paragraph_index) < len(paragraphs):
            para = paragraphs[int(paragraph_index)]
            text = para.text or ''
            local_start = max(0, int(char_start))
            local_end = min(len(text), int(char_end))
            if local_end > local_start and text[local_start:local_end] == original_text:
                return para, int(paragraph_index), local_start, local_end

    pos_start, pos_end = _parse_issue_position(_issue_value(issue, 'position', ''))
    cursor = 0
    for index, para in enumerate(paragraphs):
        text = para.text or ''
        para_start = cursor
        para_end = cursor + len(text)
        if pos_end and para_start <= pos_start < para_end + 1:
            local_start = max(0, pos_start - para_start)
            local_end = min(len(text), max(local_start + 1, pos_end - para_start))
            if text[local_start:local_end] == original_text:
                return para, index, local_start, local_end
        cursor = para_end + 1

    best_para = _find_best_docx_paragraph(paragraphs, issue)
    if best_para is None:
        return None, None, None, None
    para_index = paragraphs.index(best_para)
    text = best_para.text or ''
    local_start = text.find(original_text)
    if local_start < 0:
        lowered = text.lower()
        local_start = lowered.find(original_text.lower())
    if local_start < 0:
        return best_para, para_index, None, None
    return best_para, para_index, local_start, local_start + len(original_text)


def _add_docx_comment_marker(paragraph, comment_id, char_start=None, char_end=None):
    from lxml import etree

    p_element = paragraph._p
    w_ns = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    parts = _collect_docx_text_runs(paragraph)
    if not parts:
        return False

    start_run = parts[0][0]
    end_run = parts[-1][0]

    if char_start is not None and char_end is not None and char_start < char_end:
        for run_el, start, end, text in parts:
            if start <= char_start < end:
                if char_start > start:
                    start_run = _split_docx_run(run_el, char_start - start)
                else:
                    start_run = run_el
                break
        parts = _collect_docx_text_runs(paragraph)
        for run_el, start, end, text in parts:
            if start < char_end <= end:
                if char_end < end:
                    _split_docx_run(run_el, char_end - start)
                end_run = run_el
                break

    comment_start = etree.Element(f'{{{w_ns}}}commentRangeStart')
    comment_start.set(f'{{{w_ns}}}id', str(comment_id))
    p_element.insert(p_element.index(start_run), comment_start)

    insert_idx = p_element.index(end_run) + 1

    comment_end = etree.Element(f'{{{w_ns}}}commentRangeEnd')
    comment_end.set(f'{{{w_ns}}}id', str(comment_id))
    p_element.insert(insert_idx, comment_end)

    comment_ref_r = etree.Element(f'{{{w_ns}}}r')
    comment_ref_rpr = etree.SubElement(comment_ref_r, f'{{{w_ns}}}rPr')
    comment_ref_style = etree.SubElement(comment_ref_rpr, f'{{{w_ns}}}rStyle')
    comment_ref_style.set(f'{{{w_ns}}}val', 'CommentReference')
    comment_ref = etree.SubElement(comment_ref_r, f'{{{w_ns}}}commentReference')
    comment_ref.set(f'{{{w_ns}}}id', str(comment_id))
    p_element.insert(insert_idx + 1, comment_ref_r)
    return True


def _inject_comments_to_docx(docx_path, comments_data):
    import tempfile
    import zipfile
    from lxml import etree

    w_ns = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'

    def append_comment_line(comment_el, segments):
        p_el = etree.SubElement(comment_el, f'{{{w_ns}}}p')
        for segment in segments:
            text = str(segment.get('text', '') or '')
            if not text:
                continue
            r_el = etree.SubElement(p_el, f'{{{w_ns}}}r')
            color = str(segment.get('color', '') or '').strip()
            if color:
                r_pr = etree.SubElement(r_el, f'{{{w_ns}}}rPr')
                color_el = etree.SubElement(r_pr, f'{{{w_ns}}}color')
                color_el.set(f'{{{w_ns}}}val', color)
            t_el = etree.SubElement(r_el, f'{{{w_ns}}}t')
            if text.startswith(' ') or text.endswith(' '):
                t_el.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
            t_el.text = text

    comments_xml = etree.Element(
        f'{{{w_ns}}}comments',
        nsmap={'w': w_ns}
    )

    for cdata in comments_data:
        comment_el = etree.SubElement(
            comments_xml, f'{{{w_ns}}}comment'
        )
        comment_el.set(f'{{{w_ns}}}id', str(cdata['id']))
        comment_el.set(f'{{{w_ns}}}author', cdata['author'])
        comment_el.set(f'{{{w_ns}}}initials', cdata['initials'])

        for line in cdata.get('lines', []):
            append_comment_line(comment_el, line)

    comments_bytes = etree.tostring(comments_xml, xml_declaration=True, encoding='UTF-8', standalone=True)
    temp_dir = tempfile.mkdtemp()
    temp_output = os.path.join(temp_dir, 'output.docx')

    try:
        with zipfile.ZipFile(docx_path, 'r') as zin:
            zin.extractall(temp_dir)

        word_dir = os.path.join(temp_dir, 'word')
        with open(os.path.join(word_dir, 'comments.xml'), 'wb') as f:
            f.write(comments_bytes)

        rels_path = os.path.join(word_dir, '_rels', 'document.xml.rels')
        r_id = 'rIdComments'
        if os.path.exists(rels_path):
            rels_tree = etree.parse(rels_path)
            root = rels_tree.getroot()
            existing = root.findall('.//{http://schemas.openxmlformats.org/package/2006/relationships}Relationship')
            target_exists = False
            if existing:
                for rel in existing:
                    if rel.get('Target') == 'comments.xml':
                        r_id = rel.get('Id', r_id)
                        target_exists = True
                        break
                if not target_exists:
                    existing_ids = {rel.get('Id', '') for rel in existing}
                    next_num = 1
                    while f'rId{next_num}' in existing_ids:
                        next_num += 1
                    r_id = f'rId{next_num}'
                    new_rel = etree.SubElement(
                        root, '{http://schemas.openxmlformats.org/package/2006/relationships}Relationship'
                    )
                    new_rel.set('Id', r_id)
                    new_rel.set('Type', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments')
                    new_rel.set('Target', 'comments.xml')
                with open(rels_path, 'wb') as f:
                    f.write(etree.tostring(rels_tree, xml_declaration=True, encoding='UTF-8', standalone=True))

        doc_path = os.path.join(word_dir, 'document.xml')
        if os.path.exists(doc_path):
            doc_tree = etree.parse(doc_path)
            doc_root = doc_tree.getroot()
            body = doc_root.find('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}body')
            existing_comment_refs = body.findall('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}comments')
            if not existing_comment_refs:
                comments_ref_el = etree.SubElement(
                    body, '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}comments'
                )
                comments_ref_el.set(
                    '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id', r_id
                )
            with open(doc_path, 'wb') as f:
                f.write(etree.tostring(doc_tree, xml_declaration=True, encoding='UTF-8', standalone=True))

        with zipfile.ZipFile(temp_output, 'w', zipfile.ZIP_DEFLATED) as zout:
            for dirpath, _, filenames in os.walk(temp_dir):
                for fname in filenames:
                    full_path = os.path.join(dirpath, fname)
                    arcname = os.path.relpath(full_path, temp_dir)
                    zout.write(full_path, arcname)

        if os.path.exists(docx_path):
            os.remove(docx_path)
        shutil.move(temp_output, docx_path)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _build_review_comment_lines(issue):
    severity = str(_issue_value(issue, 'severity', 'general') or 'general').strip()
    category = str(_issue_value(issue, 'category', '') or '').strip()
    suggestion = str(_issue_value(issue, 'suggestion', '') or '').strip()
    description = str(_issue_value(issue, 'description', '') or '').strip()
    original_text = str(_issue_value(issue, 'original_text', '') or '').strip()

    rule = str(_issue_value(issue, 'rule', '') or '').strip()

    if rule in {'R002', 'HR003'}:
        suggestion_line = '在句号后补空格'
    elif '→' in suggestion:
        suggestion = suggestion.split('→', 1)[1].strip()
        suggestion_line = f"改为 {suggestion}" if suggestion else description
    else:
        suggestion = re.sub(r'^建议(?:改为|替换为|统一为|写为|使用|拆成两句：|改为：)\s*', '', suggestion)
        if suggestion.startswith('Read ') or suggestion.startswith('Click ') or suggestion.startswith('Contact '):
            suggestion_line = suggestion
        elif suggestion:
            suggestion_line = f"改为 {suggestion}" if not suggestion.startswith('改为') else suggestion
        else:
            suggestion_line = description

    lines = [[{"text": f"[{severity}] {category}".strip()}]]
    if suggestion_line:
        if suggestion_line.startswith('改为 '):
            diff_segments = _build_diff_segments(original_text, suggestion_line[3:], rule)
            lines.append([
                {"text": '改为 '},
                *diff_segments
            ])
        else:
            lines.append([{"text": suggestion_line}])
    if description and not suggestion_line:
        lines.append([{"text": description}])
    return [line for line in lines if line]


def _merge_comment_segments(segments):
    merged = []
    for segment in segments:
        text = str(segment.get('text', '') or '')
        if not text:
            continue
        color = str(segment.get('color', '') or '')
        if merged and str(merged[-1].get('color', '') or '') == color:
            merged[-1]['text'] += text
        else:
            merged.append({'text': text, 'color': color} if color else {'text': text})
    return merged


def _build_diff_segments(original_text, suggestion_text, rule=''):
    original_text = str(original_text or '')
    suggestion_text = str(suggestion_text or '')
    rule = str(rule or '')
    if not suggestion_text:
        return []

    # Full-word or full-phrase replacements read better when fully highlighted.
    if rule in {'HR002', 'HR005', 'HR008', 'HR009', 'HR010', 'R036'}:
        return [{'text': suggestion_text, 'color': 'FF0000'}]

    if rule == 'HR004':
        match = re.match(r'^(\d+(?:\.\d+)?)(.*)$', suggestion_text)
        if match:
            return _merge_comment_segments([
                {'text': match.group(1)},
                {'text': match.group(2), 'color': 'FF0000'}
            ])

    matcher = difflib.SequenceMatcher(a=original_text, b=suggestion_text)
    segments = []
    for opcode, a0, a1, b0, b1 in matcher.get_opcodes():
        text = suggestion_text[b0:b1]
        if not text:
            continue
        if opcode == 'equal':
            segments.append({'text': text})
        else:
            segments.append({'text': text, 'color': 'FF0000'})

    segments = _merge_comment_segments(segments)
    if not segments:
        return [{'text': suggestion_text, 'color': 'FF0000'}]

    if all(not segment.get('color') for segment in segments):
        return [{'text': suggestion_text, 'color': 'FF0000'}]

    return segments


def _load_review_summary(summary_text):
    if not summary_text:
        return {}
    try:
        return json.loads(summary_text)
    except Exception:
        return {}


def _find_best_docx_paragraph(paragraphs, issue):
    original = _normalize_search_text(_issue_value(issue, 'original_text', ''))
    if not original:
        return None

    best_para = None
    best_score = -1
    context_tokens = set(re.findall(r"[A-Za-z0-9\u4e00-\u9fff]+", str(_issue_value(issue, 'context', '')).lower()))

    for para in paragraphs:
        text = para.text or ''
        normalized = _normalize_search_text(text)
        if not normalized or original not in normalized:
            continue

        score = 1
        lowered = text.lower()
        if context_tokens:
            score += sum(1 for token in context_tokens if token and token in lowered)
        original_text = str(_issue_value(issue, 'original_text', '') or '')
        if original_text and original_text in text:
            score += 2
        if score > best_score:
            best_para = para
            best_score = score

    return best_para


def _enrich_docx_issue_positions(document, issues):
    from docx import Document as DocxDocument

    source_path = _get_document_upload_path(document)
    if not source_path or not source_path.exists():
        return issues

    paragraphs = list(_iter_docx_paragraphs(DocxDocument(str(source_path))))
    for issue in issues:
        para, para_index, char_start, char_end = _locate_docx_issue(paragraphs, issue)
        start, end = _parse_issue_position(issue.get('position', ''))
        if para is None or char_start is None or char_end is None:
            continue
        issue['position'] = _encode_issue_position(start, end, para_index, char_start, char_end)
    return issues


def _build_long_sentence_suggestion(sentence):
    suggestion = re.sub(r'\s+', ' ', sentence).strip().rstrip('.!?')
    if re.match(r'^If initialize successfully is displayed,', suggestion, re.IGNORECASE):
        return 'If "Initialize successfully" is displayed, the device is connected successfully. Proceed to the next step.'
    if re.match(r'^According to the number of DNB plates,', suggestion, re.IGNORECASE):
        return 'Prepare the reagents and consumables in advance according to the number of DNB plates, as shown in table 16 and figure 20.'
    if re.match(r'^This operating instruction is intended to guide operators through\b', suggestion, re.IGNORECASE):
        rewritten = re.sub(
            r'^This operating instruction is intended to guide operators through\s+',
            'This instruction guides operators through ',
            suggestion,
            flags=re.IGNORECASE,
        )
        if ' based on ' in rewritten:
            lead, basis = rewritten.split(' based on ', 1)
            return f"{lead}. It follows {basis}."
        return f"{rewritten}."
    suggestion = re.sub(r'\bplease\b', '', suggestion, flags=re.IGNORECASE)
    suggestion = re.sub(r'\bkindly\b', '', suggestion, flags=re.IGNORECASE)
    suggestion = re.sub(r'\bcan\s+be\b', 'is', suggestion, flags=re.IGNORECASE)
    suggestion = re.sub(r'\bin order to\b', 'to', suggestion, flags=re.IGNORECASE)
    suggestion = re.sub(r'\bso as to\b', 'to', suggestion, flags=re.IGNORECASE)
    suggestion = re.sub(r'\bit is recommended to\b', '', suggestion, flags=re.IGNORECASE)
    suggestion = re.sub(r'\bit is intended to\b', 'is intended to', suggestion, flags=re.IGNORECASE)
    suggestion = re.sub(r'\bthe concentration of DNB is lower than\b', 'the DNB concentration is below', suggestion, flags=re.IGNORECASE)
    suggestion = re.sub(r'\bbefore experiment\b', '', suggestion, flags=re.IGNORECASE)
    suggestion = re.sub(r'\bprior to use\b', 'before use', suggestion, flags=re.IGNORECASE)
    suggestion = re.sub(r'\buntil further use\b', 'until use', suggestion, flags=re.IGNORECASE)
    suggestion = re.sub(r'\s+,\s+', ', ', suggestion)
    suggestion = re.sub(r'\s{2,}', ' ', suggestion).strip(' ;,')
    if sentence.lower().startswith('before experiment,'):
        rewritten = sentence[len('Before experiment,'):].strip().rstrip('.!?')
        return f"{rewritten} before starting the experiment."
    if len(suggestion) > 110:
        split_point = max(suggestion.rfind(', ', 0, 110), suggestion.rfind(' and ', 0, 110))
        if split_point > 40:
            first = suggestion[:split_point].strip(' ,;')
            second = suggestion[split_point + 2:].strip(' ,;') if suggestion[split_point:split_point + 2] == ', ' else suggestion[split_point + 5:].strip(' ,;')
            if first and second:
                second = second[:1].upper() + second[1:]
                return f"{first}. {second}."
    return f"{suggestion}."


def _run_long_sentence_audit(content, file_type=None):
    if file_type == 'pdf':
        return []

    issues = []
    seen = set()
    sentence_pattern = re.compile(r'[^\n.!?]+[.!?]')
    skip_pattern = re.compile(r'^(?:contents|chapter\s+\d+|figure\s+\d+|table\s+\d+|note:|\d+[\).])', re.IGNORECASE)
    concise_trigger_pattern = re.compile(r'\b(?:before experiment|it is recommended to|in order to|as shown in|intended to guide)\b', re.IGNORECASE)
    imperative_skip_pattern = re.compile(r'^(?:click|select|open|enter|choose|read|take|place|mix|centrifuge|install|log in|log out)\b', re.IGNORECASE)
    action_hint_pattern = re.compile(r'\b(?:double-click|click|clicking|select|open|place|close|add|mix|aspirate|take out|install|log in|log out)\b', re.IGNORECASE)
    ui_step_pattern = re.compile(r'\b(?:figure\s+\d+|table\s+\d+|interface|wizard|button|door|well\b|pos\d+)\b', re.IGNORECASE)
    ui_display_pattern = re.compile(r'\b(?:will appear|will pop up|pop up)\b', re.IGNORECASE)

    for match in sentence_pattern.finditer(content):
        sentence = re.sub(r'\s+', ' ', match.group(0)).strip()
        next_fragment = content[match.end():match.end() + 12].lstrip()
        word_count = len(re.findall(r"[A-Za-z]+(?:[-'][A-Za-z]+)?", sentence))
        if word_count < 20 or skip_pattern.search(sentence) or '|' in sentence or '\t' in sentence:
            continue
        if re.search(r'\b[A-Z]\.$', sentence) and next_fragment[:1].islower():
            continue
        if imperative_skip_pattern.search(sentence) and word_count <= 35 and sentence.count(',') <= 1:
            continue
        if action_hint_pattern.search(sentence) and ui_step_pattern.search(sentence) and word_count <= 40:
            continue
        if ui_display_pattern.search(sentence) and ui_step_pattern.search(sentence) and word_count <= 35:
            continue
        if word_count <= 30 and not concise_trigger_pattern.search(sentence):
            continue
        normalized = _normalize_search_text(sentence)
        if normalized in seen:
            continue
        seen.add(normalized)
        severity = 'suggestion' if word_count <= 30 else 'general'
        issues.append({
            "severity": severity,
            "category": "句式",
            "rule": "R036",
            "chapter": extract_chapter(content, match.start()),
            "original_text": sentence,
            "context": get_context(content, match.start(), match.end(), 120),
            "suggestion": _build_long_sentence_suggestion(sentence),
            "description": "句子长度过长，建议拆分或压缩冗余表达。",
            "audit_basis": "英文技术文档写作规范 - 长句优化",
            "confidence": 90,
            "source": "rule",
            "position": _encode_issue_position(match.start(), match.end()),
        })
    return issues


def _normalize_heading_text(text):
    text = re.sub(r'\.{2,}\s*\d+$', '', str(text or '').strip())
    text = re.sub(r'\s+', ' ', text)
    return text.strip().lower()


def _run_pdf_structure_audit(content):
    issues = []
    lines = [line.strip() for line in str(content or '').splitlines()]
    if not lines:
        return issues

    toc_index = next((idx for idx, line in enumerate(lines) if line.lower() == 'contents'), -1)
    toc_entries = {}
    if toc_index >= 0:
        for line in lines[toc_index + 1:toc_index + 80]:
            if not line:
                continue
            match = re.match(r'^(\d+(?:\.\d+)*)\s+(.+?)\s*\d+$', line)
            if not match:
                if toc_entries:
                    break
                continue
            toc_entries[match.group(1)] = match.group(2).strip()

    headings = {}
    for line in lines:
        match = re.match(r'^(\d+(?:\.\d+)*)\s+(.+)$', line)
        if not match:
            continue
        section_no = match.group(1)
        title = match.group(2).strip()
        if title.isdigit():
            continue
        headings.setdefault(section_no, title)

    for section_no, title in headings.items():
        if toc_entries and section_no not in toc_entries and section_no.count('.') <= 1:
            issues.append({
                'severity': 'general',
                'category': '目录完整性',
                'rule': 'TOC-001',
                'chapter': title,
                'original_text': title,
                'context': title,
                'suggestion': f'建议将 {section_no} {title} 补充到目录中',
                'description': '正文中的一级或二级章节应在目录中列出。',
                'audit_basis': '目录完整性检查',
                'confidence': 85,
                'source': 'rule',
                'position': ''
            })
        toc_title = toc_entries.get(section_no)
        if toc_title and _normalize_heading_text(toc_title) != _normalize_heading_text(title):
            issues.append({
                'severity': 'serious',
                'category': '索引一致性',
                'rule': 'INDEX-001',
                'chapter': title,
                'original_text': toc_title,
                'context': f'目录: {toc_title} | 正文: {title}',
                'suggestion': f'建议统一为 {title}',
                'description': '目录条目名称应与正文章节标题完全一致。',
                'audit_basis': '索引一致性检查',
                'confidence': 90,
                'source': 'rule',
                'position': ''
            })

    seen_duplicate_lines = set()
    for line in lines:
        compact = re.sub(r'\s+', ' ', line).strip()
        looks_like_header = len(compact) <= 40 and len(compact.split()) <= 6
        if compact.lower() == 'version date version':
            continue
        if looks_like_header and re.search(r'\bVersion\b.*\bVersion\b', line, re.IGNORECASE):
            normalized = line.lower()
            if normalized in seen_duplicate_lines:
                continue
            seen_duplicate_lines.add(normalized)
            confidence = 82
            issues.append({
                'severity': 'suggestion' if confidence < 85 else 'general',
                'category': '表格规范',
                'rule': 'TABLE-001',
                'chapter': '',
                'original_text': line,
                'context': line,
                'suggestion': '建议删除重复的表头列名',
                'description': '表格表头中不应出现重复列名。',
                'audit_basis': '表头重复检查',
                'confidence': confidence,
                'source': 'rule',
                'position': ''
            })

    return issues


def _build_review_export_filename(doc_name, review_id, suffix):
    stem = Path(doc_name or f"review_{review_id}").stem
    safe = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff._-]+", "_", stem).strip("_") or f"review_{review_id}"
    return f"{safe}_审核结果_{review_id}{suffix}"


def _get_document_upload_path(document):
    candidate = UPLOAD_DIR / (document.filename or "")
    if candidate.exists():
        return candidate
    return None


def _select_export_issues(issues):
    preferred = [i for i in issues if getattr(i, 'status', None) in (None, '', 'pending', 'confirmed', 'converted_to_rule')]
    return sorted(preferred or list(issues), key=_issue_sort_key)


def _format_review_mode(mode):
    return {
        "hybrid": "混合审核（规则 + 拼写 + AI）",
        "rule": "规则审核",
        "ai": "AI审核",
    }.get(mode or "", mode or "-")


def _format_issue_source(source):
    return {
        "rule": "规则",
        "term": "术语",
        "ai": "AI",
        "spellcheck": "拼写检查",
        "grammar": "语法检查",
    }.get(source or "", source or "-")


def _format_issue_severity(severity):
    return {
        "fatal": "致命",
        "serious": "严重",
        "general": "一般",
        "suggestion": "建议",
    }.get(severity or "general", (severity or "general").upper())


def _highlight_issue_context(issue):
    context = str(getattr(issue, "context", "") or "")
    original = str(getattr(issue, "original_text", "") or "")
    if not context:
        return "-"

    escaped_context = html_lib.escape(context)
    if not original:
        return escaped_context.replace("\n", "<br>")

    escaped_original = html_lib.escape(original)
    pattern = re.compile(re.escape(escaped_original), re.IGNORECASE)
    highlighted = pattern.sub('<span class="problem-highlight">\\g<0></span>', escaped_context, count=1)
    return highlighted.replace("\n", "<br>")


def _generate_review_html_content(review, doc, issues):
    summary = _load_review_summary(review.summary)
    confirmed = [i for i in issues if i.status == "confirmed"]
    false_pos = [i for i in issues if i.status == "false_positive"]
    pending = [i for i in issues if i.status in ["pending", None]]
    ignored = [i for i in issues if i.status == "ignored"]
    doc_name = doc.filename if doc else f"文档{review.document_id}"

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>审核报告 - {doc_name}</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{ font-family: 'Microsoft YaHei', Arial, sans-serif; margin: 0; padding: 20px; background: #f5f7fa; color: #333; }}
        .container {{ max-width: 1100px; margin: 0 auto; background: #fff; padding: 30px 40px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
        h1 {{ color: #2c3e50; border-bottom: 3px solid #409eff; padding-bottom: 10px; }}
        h2 {{ color: #409eff; margin-top: 30px; }}
        .meta {{ background: #f8f9fa; padding: 15px; border-left: 4px solid #409eff; margin: 20px 0; }}
        .meta-row {{ margin: 5px 0; }}
        .meta-label {{ font-weight: bold; color: #555; display: inline-block; width: 100px; }}
        .summary-grid {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin: 20px 0; }}
        .summary-card {{ padding: 15px; text-align: center; border-radius: 4px; color: #fff; }}
        .summary-card .num {{ font-size: 28px; font-weight: bold; }}
        .summary-card .label {{ font-size: 12px; margin-top: 5px; }}
        .card-total {{ background: #409eff; }}
        .card-confirmed {{ background: #67c23a; }}
        .card-false {{ background: #909399; }}
        .card-pending {{ background: #e6a23c; }}
        .card-ignored {{ background: #c0c4cc; }}
        .issue {{ border: 1px solid #e4e7ed; border-radius: 4px; padding: 15px 20px; margin: 12px 0; background: #fff; }}
        .issue.confirmed {{ border-left: 5px solid #67c23a; background: #f0f9eb; }}
        .issue.false_positive {{ border-left: 5px solid #909399; background: #f4f4f5; opacity: 0.7; }}
        .issue.ignored {{ border-left: 5px solid #c0c4cc; background: #fafafa; opacity: 0.6; }}
        .issue.pending {{ border-left: 5px solid #e6a23c; }}
        .issue-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }}
        .issue-title {{ font-weight: bold; color: #303133; }}
        .badge {{ display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 12px; color: #fff; margin-left: 6px; }}
        .badge-confirmed {{ background: #67c23a; }}
        .badge-false {{ background: #909399; }}
        .badge-pending {{ background: #e6a23c; }}
        .badge-ignored {{ background: #c0c4cc; }}
        .badge-severity-fatal {{ background: #f56c6c; }}
        .badge-severity-serious {{ background: #e6a23c; }}
        .badge-severity-general {{ background: #909399; }}
        .badge-severity-suggestion {{ background: #67c23a; }}
        .issue-field {{ margin: 6px 0; font-size: 14px; }}
        .issue-label {{ font-weight: bold; color: #606266; display: inline-block; min-width: 80px; }}
        .original-text {{ background: #fef0f0; padding: 4px 8px; border-radius: 3px; color: #c45656; font-family: 'Courier New', monospace; }}
        .suggestion {{ background: #f0f9eb; padding: 4px 8px; border-radius: 3px; color: #5a8e3f; }}
        .context {{ color: #444; font-size: 13px; line-height: 1.7; white-space: normal; }}
        .problem-highlight {{ color: #d93025; background: #fff1f0; font-weight: 700; padding: 1px 3px; border-radius: 3px; }}
        .subtle {{ color: #909399; font-size: 12px; }}
        .empty {{ text-align: center; color: #909399; padding: 40px; }}
        .footer {{ margin-top: 40px; text-align: center; color: #909399; font-size: 12px; border-top: 1px solid #ebeef5; padding-top: 20px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>智能技术文档审核报告</h1>
        <div class="meta">
            <div class="meta-row"><span class="meta-label">文档名称:</span> {doc_name}</div>
            <div class="meta-row"><span class="meta-label">审核任务:</span> #{review.id}</div>
            <div class="meta-row"><span class="meta-label">文档类型:</span> {getattr(doc, 'file_type', '') or '-'}</div>
            <div class="meta-row"><span class="meta-label">审核模式:</span> {_format_review_mode(review.mode)}</div>
            <div class="meta-row"><span class="meta-label">审核时间:</span> {review.created_at}</div>
            <div class="meta-row"><span class="meta-label">问题总数:</span> {summary.get('total', len(issues))}</div>
            <div class="meta-row"><span class="meta-label">报告生成:</span> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
        </div>

        <h2>审核概览</h2>
        <div class="summary-grid">
            <div class="summary-card card-total"><div class="num">{len(issues)}</div><div class="label">发现问题</div></div>
            <div class="summary-card card-confirmed"><div class="num">{len(confirmed)}</div><div class="label">已确认</div></div>
            <div class="summary-card card-false"><div class="num">{len(false_pos)}</div><div class="label">误报</div></div>
            <div class="summary-card card-pending"><div class="num">{len(pending)}</div><div class="label">待确认</div></div>
            <div class="summary-card card-ignored"><div class="num">{len(ignored)}</div><div class="label">已忽略</div></div>
        </div>
"""

    if not issues:
        html += '<div class="empty">未发现任何问题</div>'
    else:
        html += '<h2>问题详情 (共 {0} 条)</h2>'.format(len(issues))
        order = {"confirmed": 0, "pending": 1, None: 1, "": 1, "false_positive": 2, "ignored": 3}
        sorted_issues = sorted(issues, key=lambda i: (order.get(i.status, 1), i.id))

        for issue in sorted_issues:
            sev_class = f"badge-severity-{issue.severity or 'general'}"
            issue_status = issue.status or "pending"
            status_class = {
                "confirmed": "badge-confirmed",
                "false_positive": "badge-false",
                "ignored": "badge-ignored",
                "pending": "badge-pending"
            }.get(issue_status, "badge-pending")
            status_text = {
                "confirmed": "已确认",
                "false_positive": "误报",
                "ignored": "已忽略",
                "pending": "待确认"
            }.get(issue_status, "待确认")

            html += f"""
        <div class="issue {issue_status}">
            <div class="issue-header">
                <div class="issue-title">问题 #{issue.id} - {issue.category or '未分类'}</div>
                <div>
                    <span class="badge {sev_class}">{_format_issue_severity(issue.severity)}</span>
                    <span class="badge {status_class}">{status_text}</span>
                </div>
            </div>
            <div class="issue-field"><span class="issue-label">规则:</span> {issue.rule or '-'}</div>
            <div class="issue-field"><span class="issue-label">章节:</span> {issue.chapter or '-'}</div>
            <div class="issue-field"><span class="issue-label">原文:</span> <span class="context">{_highlight_issue_context(issue)}</span></div>
            <div class="issue-field subtle"><span class="issue-label">命中内容:</span> <span class="original-text">{html_lib.escape(issue.original_text or '')}</span></div>
            <div class="issue-field"><span class="issue-label">建议:</span> <span class="suggestion">{issue.suggestion or '-'}</span></div>
            <div class="issue-field"><span class="issue-label">依据:</span> {issue.audit_basis or '-'}</div>
            <div class="issue-field"><span class="issue-label">置信度:</span> {issue.confidence or 0}% | <span class="issue-label">来源:</span> {_format_issue_source(issue.source)}</div>
        </div>
"""

    html += f"""
        <div class="footer">由 智能技术文档审核平台 生成 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
    </div>
</body>
</html>"""
    return html


def _export_review_docx(review, document, issues):
    from docx import Document as DocxDocument

    source_path = _get_document_upload_path(document)
    if not source_path or not source_path.exists():
        raise HTTPException(status_code=404, detail="原始 Word 文件不存在")

    REVIEW_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    export_name = _build_review_export_filename(document.filename, review.id, ".docx")
    export_path = REVIEW_EXPORT_DIR / export_name
    shutil.copyfile(source_path, export_path)

    doc = DocxDocument(str(export_path))
    paragraphs = list(_iter_docx_paragraphs(doc))
    comments_data = []
    comment_id = 0

    for issue in _select_export_issues(issues):
        target_para, _, char_start, char_end = _locate_docx_issue(paragraphs, issue)
        if target_para is None or char_start is None or char_end is None:
            continue
        comment_id += 1
        if _add_docx_comment_marker(target_para, comment_id, char_start, char_end):
            comments_data.append({
                "id": comment_id,
                "author": "智能技术文档审核",
                "initials": "RV",
                "lines": _build_review_comment_lines(issue),
            })

    if not comments_data:
        raise HTTPException(status_code=400, detail="未能在 Word 文档中定位可批注的审核问题")

    doc.save(str(export_path))
    _inject_comments_to_docx(str(export_path), comments_data)
    return export_path, export_name, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _export_review_html_file(review, document, issues):
    REVIEW_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    export_name = _build_review_export_filename(document.filename if document else "review", review.id, ".html")
    export_path = REVIEW_EXPORT_DIR / export_name
    html = _generate_review_html_content(review, document, issues)
    export_path.write_text(html, encoding="utf-8")
    return export_path, export_name, "text/html; charset=utf-8"


def _run_english_heuristic_audit(content, file_type=None):
    issues = []
    seen = set()
    allowed_ui_commands = {
        'tap save', 'tap confirm', 'tap cancel', 'tap delete',
        'click ok', 'click cancel', 'click save',
        'press enter', 'press ok',
    }

    def add_issue_by_span(start, end, original_text, rule, category, suggestion, description, audit_basis, severity="general"):
        original_text = str(original_text or "").strip()
        if not original_text:
            return
        key = (rule, _normalize_search_text(original_text), start)
        if key in seen:
            return
        seen.add(key)
        issues.append({
            "severity": severity,
            "category": category,
            "rule": rule,
            "chapter": extract_chapter(content, start),
            "original_text": original_text,
            "context": get_context(content, start, end, 160),
            "suggestion": suggestion,
            "description": description,
            "audit_basis": audit_basis,
            "confidence": 92,
            "source": "rule",
            "position": _encode_issue_position(start, end),
        })

    def add_issue(match, rule, category, suggestion, description, audit_basis, severity="general"):
        add_issue_by_span(match.start(), match.end(), match.group(0), rule, category, suggestion, description, audit_basis, severity)

    for match in re.finditer(r"https?://en\.mgi-tech\.com", content, re.IGNORECASE):
        add_issue(match, "HR001", "合规", "建议替换为 https://global-mgitech.com", "海外英文文档中官网地址应使用海外官网域名。", "公司特定规范 - 海外官网地址", "serious")

    for match in re.finditer(r"\bdesk\s+top\b", content, re.IGNORECASE):
        add_issue(match, "HR002", "英文规范", "建议改为 desktop", "desktop 在该语境中应使用合成词写法。", "英文技术文档写作规范 - 拼写")

    if file_type != "pdf":
        for match in re.finditer(r"(?<=[A-Za-z0-9\)])\.(?=[A-Z])", content):
            original = content[match.start():min(len(content), match.start() + 2)]
            suggestion = f"建议改为 {original[0]} {original[1:]}" if len(original) == 2 else "建议在句号后补一个空格"
            add_issue_by_span(match.start(), min(len(content), match.start() + len(original)), original, "HR003", "格式", suggestion, "英文正文中的句号后应保留空格。", "英文技术文档写作规范 - 标点与空格")

    for match in re.finditer(r"(?<![A-Za-z0-9.])\d+(?:\.\d+)?(?:mL|μL|uL|ng/μL|mg|mm|cm|kg)\b", content):
        original = match.group(0)
        unit_match = re.match(r"(\d+(?:\.\d+)?)(.+)", original)
        if not unit_match:
            continue
        suggestion = f"建议改为 {unit_match.group(1)} {unit_match.group(2)}"
        add_issue(match, "HR004", "单位", suggestion, "数字与单位之间应保留空格。", "英文技术文档写作规范 - 单位格式", "serious")

    for match in re.finditer(r"\bWeLL\b", content):
        add_issue(match, "HR005", "格式", "建议统一为 Well", "单词内部大小写形式不一致。", "技术文档常见错误清单 - 格式一致性", "serious")

    range_unit_pattern = r"(?:ng/μL|μL|uL|mL|mg|mm|cm|℃|°C|%)"
    for match in re.finditer(rf"\b\d+(?:\.\d+)?\s*{range_unit_pattern}\s*-\s*\d+(?:\.\d+)?\s*{range_unit_pattern}\b", content):
        text = match.group(0)
        suggestion = re.sub(r"\s*-\s*", " to ", text)
        add_issue(match, "HR006", "格式", f"建议改为 {suggestion}", "英文数值范围建议使用 to 表达范围。", "英文技术文档写作规范 - 范围表达", "serious")

    for match in re.finditer(r"greater than upper limit range", content, re.IGNORECASE):
        add_issue(match, "HR007", "语法", "建议改为 greater than the upper limit range", "该短语前缺少定冠词 the。", "英文技术文档写作规范 - 冠词", "serious")

    please_replacements = {
        'please contact': 'contact technical support',
        'please use with caution': 'Use with caution',
        'please adjust moderately': 'Adjust moderately',
    }
    for phrase, replacement in please_replacements.items():
        for match in re.finditer(rf"\b{re.escape(phrase)}\b", content, re.IGNORECASE):
            add_issue(match, "HR008", "风格", f"建议改为 {replacement}", "技术文档建议使用直接的客观表达。", "英文技术文档写作规范 - 语气")

    for match in re.finditer(r"\bafter login in\b", content, re.IGNORECASE):
        add_issue(match, 'GRAMMAR-001', '语法', '建议改为 after logging in', 'login 作为动作时应使用 logging in。', '英语语法规范 - 动作表达', 'serious')

    for match in re.finditer(r"\bafter login\b(?!\s+in\b)", content, re.IGNORECASE):
        context = get_context(content, match.start(), match.end(), 40).lower()
        if re.search(r'\b(?:the|you|the software|the device|tap|click|press|can|will|is|are|automatically)\b', context):
            add_issue(match, 'GRAMMAR-002', '语法', '建议改为 after logging in', 'login 作为动作时应使用 logging in。', '英语语法规范 - 动作表达', 'serious')

    if file_type != 'pdf':
        for match in re.finditer(r"\blog\s*in\b(?!\s+order\b)", content, re.IGNORECASE):
            add_issue(match, "HR009", "一致性", "建议统一为 log in 或 login，并与界面名词/动作语境保持一致", "登录相关表达应区分动作和名词。", "英文技术文档写作规范 - 术语一致性")

    if file_type != 'pdf':
        for match in re.finditer(r"\blog\s*out\b", content, re.IGNORECASE):
            add_issue(match, "HR010", "一致性", "建议统一为 log out 或 logout，并与界面名词/动作语境保持一致", "退出登录相关表达应区分动作和名词。", "英文技术文档写作规范 - 术语一致性")

    for match in re.finditer(r"\b\d+(?:\.\d+)?\s*[xX]\s*\d+(?:\.\d+)?\b", content):
        add_issue(match, "HR011", "格式", f"建议改为 {match.group(0).replace('x', ' × ').replace('X', ' × ')}", "乘号建议使用 × 并保留两侧空格。", "英文技术文档写作规范 - 数学符号")

    for match in re.finditer(r"\b(?:www\.)?mgitech\.cn\b", content, re.IGNORECASE):
        add_issue(match, "HR012", "合规", "建议改为 global-mgitech.com", "海外英文文档中官网域名应统一。", "公司特定规范 - 海外官网地址", "serious")

    for match in re.finditer(r"\b(?:e-?mail|Email)\s*:", content):
        add_issue(match, "HR013", "格式", "建议统一为 Email:", "联系方式标签建议统一大小写。", "英文技术文档写作规范 - 标签格式")

    for match in re.finditer(r"\b(?:web site|website address)\b", content, re.IGNORECASE):
        add_issue(match, "HR014", "一致性", "建议统一为 website", "网站相关名词建议统一。", "英文技术文档写作规范 - 术语一致性")

    for match in re.finditer(r"\bcharaters\b|\bcharater\b|\boccured\b|\bocurred\b|\btecnical\b|\bseperate\b|\bmaintenence\b|\bmaintanance\b|\breferrence\b|\brefered\b|\brefering\b|\buntill\b|\buseing\b|\bwheras\b|\bwich\b|\bdefination\b|\bdesciption\b|\brecieve\b", content, re.IGNORECASE):
        replacements = {
            'charaters': 'characters',
            'charater': 'character',
            'occured': 'occurred',
            'ocurred': 'occurred',
            'tecnical': 'technical',
            'seperate': 'separate',
            'maintenence': 'maintenance',
            'maintanance': 'maintenance',
            'referrence': 'reference',
            'refered': 'referred',
            'refering': 'referring',
            'untill': 'until',
            'useing': 'using',
            'wheras': 'whereas',
            'wich': 'which',
            'defination': 'definition',
            'desciption': 'description',
            'recieve': 'receive',
        }
        replacement = replacements.get(match.group(0).lower(), '')
        add_issue(match, 'SPELL-001', '拼写/用词错误', f'建议改为 {replacement}', '发现常见高置信拼写错误。', '常见拼写错误清单', 'serious')

    if file_type != 'pdf':
        for match in re.finditer(r"\bTap\s+(?!to\b|the\b|a\b|an\b)([A-Za-z]+)\b", content):
            if match.group(0).lower() in allowed_ui_commands:
                continue
            action = match.group(1)
            if action[:1].isupper() or action.isupper() or len(action) <= 2:
                continue
            add_issue(match, 'STYLE-002', '风格', f'建议改为 Tap to {action.lower()}', 'Tap 后建议使用 to 引导动作。', '交互文案规范', 'general')

    for match in re.finditer(r"Performing the following steps", content, re.IGNORECASE):
        add_issue(match, 'STYLE-003', '风格', '建议改为 Perform the following steps', '祈使句建议直接使用动词原形。', '技术文档句式规范', 'general')

    for match in re.finditer(r"[\u3001\u3002\uff0c\uff1b\uff1a\uff08\uff09]", content):
        add_issue(match, 'PUNCT-001', '标点符号', '建议改为对应的半角英文标点', '英文文档中不应混入全角或中文标点。', '英文标点规范', 'serious')

    if file_type != 'pdf':
        for match in re.finditer(r"\bwill\s+(?:be\s+)?\w+(?:ed|en)\b", content, re.IGNORECASE):
            add_issue(match, 'TENSE-001', '时态', '建议改为一般现在时表达', '技术文档通常使用一般现在时。', '技术文档时态规范', 'general')

    if file_type != 'pdf' and re.search(r'\bTap\b', content) and re.search(r'\b[Cc]lick\b', content):
        for match in re.finditer(r"\b[Cc]lick\b", content):
            phrase = str(content[match.start():min(len(content), match.end() + 8)]).split('\n', 1)[0].strip().lower()
            if any(phrase.startswith(command) for command in allowed_ui_commands if command.startswith('click ')):
                continue
            add_issue(match, 'TERM-001', '术语一致性', '建议统一为 Tap', '触屏设备中的操作用语建议统一使用 Tap。', '触屏交互术语规范', 'general')

    return issues


def get_knowledge_basis(db: Session):
    basis_list = []
    try:
        tree = get_folder_tree(db, None)
        for folder in tree:
            folder_obj = get_folder(db, folder.id)
            if folder_obj:
                files = get_folder_files(db, folder.id)
                for file in files:
                    basis_list.append({
                        "title": file.name,
                        "folder": folder.name,
                        "path": f"{folder.name}/{file.name}"
                    })
    except Exception as e:
        print(f"获取知识库审核依据失败: {e}")
    return basis_list


def extract_chapter(content, position):
    lines = content[:position].split('\n')
    for i in range(len(lines) - 1, max(0, len(lines) - 20), -1):
        line = lines[i].strip()
        if not line:
            continue
        if line.startswith('#'):
            return line.lstrip('#').strip()
        if re.match(r'^\d+(?:\.\d+)*(?:[\)\.])?\s*[A-Z][^\n]{2,}$', line):
            return re.sub(r'^(\d+(?:\.\d+)*)([A-Z])', r'\1 \2', line)
        if re.match(r'^(?:Chapter|Section)\s+\d+[\s:.-]+', line, re.IGNORECASE):
            return line
    return ""


def get_context(content, start, end, context_length=200):
    start_idx = max(0, start - context_length)
    end_idx = min(len(content), end + context_length)
    context = content[start_idx:end_idx]
    if start_idx > 0:
        context = "..." + context
    if end_idx < len(content):
        context = context + "..."
    return context


@router.get("/", response_model=list[Review])
async def list_reviews(db: Session = Depends(get_db)):
    reviews = get_reviews(db)
    result = []
    for review in reviews:
        doc = get_document(db, document_id=review.document_id)
        review_dict = review.__dict__.copy()
        review_dict['document_name'] = doc.filename if doc else ''
        review_dict['document_file_type'] = doc.file_type if doc else ''
        if not review_dict.get('summary'):
            review_dict['summary'] = '{}'
        # 添加进度信息
        if review.status == 'running':
            progress = get_progress(review.id)
            review_dict['progress'] = progress
        result.append(review_dict)
    return result


@router.get("/{review_id}/progress")
async def get_review_progress(review_id: int):
    return get_progress(review_id)


def detect_language(content):
    chinese_chars = re.findall(r'[\u4e00-\u9fff]', content)
    english_chars = re.findall(r'[a-zA-Z]', content)

    if len(chinese_chars) > len(english_chars) * 2:
        return "cn"
    elif len(english_chars) > len(chinese_chars) * 2:
        return "en"
    return "both"


# ------------------------------------------------------------------
# 误报白名单: 常见合法英文缩写 / 公司名 / 术语 (避免简单正则误报)
# ------------------------------------------------------------------
_EN_ABBREV_ALLOWED = [
    "Ltd.", "Co.", "Inc.", "LLC.", "LLP.", "Corp.",
    "Mr.", "Mrs.", "Ms.", "Dr.", "Prof.",
    "e.g.", "i.e.", "etc.", "et al.",
    "P.R.", "R.P.", "U.S.A.", "U.K.", "U.S.",
    "vs.", "etc", "sq.",
]


def _in_abbreviation_allowed(text):
    t = text.strip()
    for a in _EN_ABBREV_ALLOWED:
        if t.lower() == a.lower() or t.lower().endswith(a.lower()):
            return True
    return False


_TECH_TERMS = {
    'prep', 'device', 'consumables', 'reagents', 'extraction', 'extent', 'selection',
    'mg', 'ml', 'ul', 'μg', 'μl', 'kb', 'mb', 'gb', 'nm', 'mm', 'cm',
    'dna', 'rna', 'pcr', 'elisa', 'atp', 'cdna', 'mrna', 'trna',
    'buffer', 'solution', 'kit', 'system', 'assay', 'protocol', 'procedure',
    'sample', 'specimen', 'tube', 'plate', 'well', 'tip', 'pipette',
    'centrifuge', 'incubator', 'shaker', 'homogenizer', 'lyser',
    'volume', 'concentration', 'temperature', 'time', 'rpm', 'min', 'hr',
    'mgisp', 'bgiseq', 'dnbseq', 'dnb', 'cpas', 'coolmps',
    'quality', 'control', 'standard', 'reference', 'calibration', 'validation',
    'protocol', 'method', 'technique', 'approach', 'strategy', 'step',
}


def _is_tech_term(word):
    return word.lower() in _TECH_TERMS


def _is_sentence_start(content, position):
    before = content[max(0, position - 20):position]
    return before.strip().endswith('.') or before.strip().endswith('!') or before.strip().endswith('?') or position == 0


_DISABLED_RULES_FOR_REVIEW = {
    # These rules describe style preferences, file-level properties, or consistency checks
    # that cannot be reliably determined by a single regex hit in extracted document text.
    "R017", "R018", "R019", "R037", "R039", "R040",
    "R042", "R043", "R044", "R045", "R048", "R050",
}


def _should_skip_rule_match(rule, match, content, document_language, file_type=None):
    rule_no = getattr(rule, "rule_no", "")
    original_text = match.group()
    start = match.start()
    end = match.end()
    context = content[max(0, start - 40):min(len(content), end + 40)]

    if rule_no in _DISABLED_RULES_FOR_REVIEW:
        return True

    if file_type == "pdf" and rule_no in {"R002", "R013", "R036"}:
        return True

    # Numeric punctuation inside decimals, versions, and enumerations is usually valid.
    if rule_no == "R001":
        if re.search(r"\d[\.,]\d", context):
            return True

    if rule_no == "R002":
        if re.fullmatch(r"\.[a-z]", original_text):
            return True
        if any(ext in context.lower() for ext in [".xml", ".wfex", ".sp960", "@", ".com"]):
            return True

    if rule_no == "R004":
        if len(original_text) > 80 or "\n" in original_text:
            return True

    # Quotation direction regex currently matches normal quoted text too often.
    if rule_no == "R007":
        return True

    # Trademark markers are common inline forms in extracted text and need richer formatting context.
    if rule_no == "R008":
        return True

    # Unit spacing rule should not flag model numbers, percentages, temperatures without unit intent, or compact codes.
    if rule_no == "R013":
        if original_text.endswith('%') or re.fullmatch(r"\d+(?:\.\d+)?[Vv]", original_text):
            return True
        if re.search(r"[A-Z]{2,}\d|\d[A-Z]{2,}", original_text):
            return True

    if rule_no == "R011":
        if "/" in context or "rpm/min" in context.lower():
            return True

    if rule_no == "R021":
        if ".com" in context.lower() or "@" in context or "http" in context.lower() or any(ext in context.lower() for ext in [".xml", ".json", ".txt", ".docx", ".pdf"]):
            return True

    if rule_no == "R023":
        if not original_text.lower().startswith("a "):
            return True

    if rule_no == "R024":
        tokens = original_text.split()
        if original_text.strip().lower() == "none none":
            return True
        if any(any(ch.isdigit() for ch in token) for token in tokens):
            return True
        if tokens and all(len(token) <= 1 for token in tokens):
            return True

    # Mixed Chinese-English spacing rule should keep common product names and protocol acronyms intact.
    if rule_no == "R025":
        if re.search(r"[A-Z]{2,}|[A-Za-z]+\d|\d+[A-Za-z]+", original_text):
            return True

    # Markdown/code formatting rules only apply when the extracted text still clearly shows markdown structure.
    if rule_no in {"R030", "R031", "R032", "R033", "R034", "R046", "R047", "R049"}:
        if "```" not in content and "#" not in content and "[" not in content and "](" not in content:
            return True

    # Long-sentence rules are too noisy on table rows, lists, and extracted fragments.
    if rule_no == "R036":
        return True

    if rule_no == "R035":
        line = content[max(0, start - 120):min(len(content), end + 120)]
        if "|" in line or re.search(r"\b(?:Figure|Table|Step|Note|WARNING|CAUTION)\b", line, re.IGNORECASE):
            return True

    return False


def run_rule_audit(content, rules, knowledge_basis=None, file_type=None):
    """规则审核: 基于正则, 加上简易白名单过滤, 按内容去重"""
    issues = []
    document_language = detect_language(content)
    seen_keys = set()

    for rule in rules:
        try:
            if rule.language == "cn" and document_language == "en":
                continue
            if rule.language == "en" and document_language == "cn":
                continue

            matches = list(re.finditer(rule.regex, content))
            for match in matches:
                original_text = match.group()

                if _should_skip_rule_match(rule, match, content, document_language, file_type):
                    continue

                if document_language in ("en", "both") and _in_abbreviation_allowed(original_text):
                    continue

                if rule.rule_no in ("R021", "R022"):
                    if _is_tech_term(original_text):
                        continue
                    if rule.rule_no == "R021" and not _is_sentence_start(content, match.start()):
                        continue

                chapter = extract_chapter(content, match.start())
                norm_text = re.sub(r"\s+", "", original_text).lower()
                dedup_key = f"{rule.rule_no}|{norm_text}|{chapter}"
                if dedup_key in seen_keys:
                    continue
                seen_keys.add(dedup_key)

                context = get_context(content, match.start(), match.end(), 200)

                basis = rule.audit_basis if rule.audit_basis else ""
                if not basis and knowledge_basis:
                    for kb in knowledge_basis:
                        if any(kw.lower() in rule.description.lower() for kw in ["标点", "格式", "术语", "写作"]):
                            if any(name in kb["title"] for name in ["风格指南", "写作规范", "手册", "指南"]):
                                basis = kb["path"]
                                break

                issues.append({
                    "severity": "general",
                    "category": rule.category or "其他",
                    "rule": rule.rule_no,
                    "chapter": chapter,
                    "original_text": original_text,
                    "context": context,
                    "suggestion": rule.suggestion if rule.suggestion else "",
                    "description": rule.description or "",
                    "audit_basis": basis if basis else "技术文档写作规范",
                    "confidence": 100,
                    "source": "rule",
                    "position": _encode_issue_position(match.start(), match.end())
                })
        except Exception as e:
            print(f"规则 {getattr(rule,'rule_no','?')} 匹配出错: {e}")
            continue
    return issues


def run_term_check(content, terms):
    """术语检查: 按归一化原文去重"""
    issues = []
    if not terms:
        return issues

    seen_keys = set()
    for term in terms:
        try:
            if not term.non_standard:
                continue
            occurrences = list(re.finditer(re.escape(term.non_standard), content))
            for match in occurrences:
                chapter = extract_chapter(content, match.start())
                norm_text = re.sub(r"\s+", "", term.non_standard).lower()
                dedup_key = f"TERM|{norm_text}|{chapter}"
                if dedup_key in seen_keys:
                    continue
                seen_keys.add(dedup_key)

                context = get_context(content, match.start(), match.end(), 200)
                issues.append({
                    "severity": "suggestion",
                    "category": "术语规范",
                    "rule": "TERM",
                    "chapter": chapter,
                    "original_text": term.non_standard,
                    "context": context,
                    "suggestion": f"建议使用标准术语: {term.standard}",
                    "description": f"发现非标准术语: {term.non_standard}",
                    "audit_basis": "MGI中文技术文档写作风格指南 - 缩略语",
                    "confidence": 95,
                    "source": "term",
                    "position": _encode_issue_position(match.start(), match.end())
                })
        except Exception as e:
            print(f"术语 {getattr(term, 'non_standard', '?')} 匹配出错: {e}")
            continue
    return issues


def dedupe_issues_by_original(issues):
    """按 '分类 + 归一化原文 + 位置相近' 合并, 并保留出现次数最多的项"""
    if not issues:
        return []
    
    # 误报过滤 - 已知无效的模式
    FALSE_POSITIVE_PATTERNS = [
        re.compile(r'^[×±÷∞∑∏∫°℃℉]$'),  # 纯数学符号
        re.compile(r'^[\d\.]+$'),  # 纯数字
        re.compile(r'^[A-Z]{1,3}$'),  # 1-3个大写字母（避免误报为单词错误）
        re.compile(r'^[\.,;:\?!]+$'),  # 纯标点
    ]
    
    def is_false_positive(text):
        text = str(text).strip()
        if not text:
            return True
        allowed_single_punctuations = {'.', ',', ';', ':', '!', '?', '(', ')', '[', ']', '{', '}', '：', '，', '。', '；', '（', '）', '“', '”', '‘', '’', '、'}
        if len(text) < 2 and text not in allowed_single_punctuations:
            return True
        for pat in FALSE_POSITIVE_PATTERNS:
            if pat.match(text):
                return True
        return False
    
    # 第一步：过滤已知误报
    filtered = [i for i in issues if not is_false_positive(i.get('original_text', ''))]
    print(f"[审核] 误报过滤: 过滤 {len(issues) - len(filtered)} 个, 剩余 {len(filtered)} 个")
    
    def issue_rank(issue):
        source = issue.get("source", "")
        severity = issue.get("severity", "general")
        confidence = issue.get("confidence", 0) or 0
        severity_rank = {"fatal": 4, "serious": 3, "general": 2, "suggestion": 1}.get(severity, 0)
        source_rank = {"rule": 3, "term": 2, "ai": 1}.get(source, 0)
        return (severity_rank, source_rank, confidence)

    # 第二步：去重（优先按原文+章节聚合，避免规则与 AI 对同一问题重复上报）
    seen = {}
    for issue in filtered:
        norm = re.sub(r"\s+", "", str(issue.get("original_text", ""))).lower()
        chapter = issue.get("chapter", "")
        source = issue.get("source", "")
        rule = issue.get("rule", "")
        key = f"{norm}|{chapter}"
        if source == 'spellcheck' or rule == 'SPELL':
            key = f"spell|{norm}"
        if rule in {'STYLE-003', 'HR008', 'GRAMMAR-001', 'GRAMMAR-002'}:
            key = f"{rule}|{norm}|{issue.get('position', '')}"
        if not norm.strip():
            continue
        if key in seen:
            old = seen[key]
            if issue_rank(issue) > issue_rank(old):
                seen[key] = issue
        else:
            seen[key] = issue
    return list(seen.values())


def _run_review_background(review_id: int, document_id: int, mode: str):
    """后台执行审核任务（带进度更新）"""
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        set_progress(review_id, 'running', '加载文档', 5, '正在读取文档内容...')
        
        document = get_document(db, document_id=document_id)
        if not document:
            set_progress(review_id, 'failed', '文档不存在', 0, f'文档ID={document_id}不存在')
            update_review_status(db, review_id, "failed", 0, "Document not found")
            return

        issues = []
        content = document.content or ""
        if document.file_type == 'pdf':
            content = clean_pdf_text(content)
        content_limit = 120000 if document.file_type == 'pdf' else 20000
        content = content[:content_limit]
        document_language = detect_language(content)
        print(f"[审核] 文档ID={document_id}, 语言检测={document_language}, 内容长度={len(content)}字符")

        knowledge_basis = get_knowledge_basis(db)
        has_ai_client = ai_client.has_any_client
        print(f"[审核] AI客户端可用: {has_ai_client}, 模式={mode}")

        if mode in ["rule", "hybrid"]:
            set_progress(review_id, 'running', '规则审核', 15, '正在加载审核规则...')
            rules = get_rules(db)
            print(f"[审核] 加载规则数量: {len(rules)}")
            
            set_progress(review_id, 'running', '规则审核', 25, '正在执行规则匹配...')
            rule_issues = run_rule_audit(content, rules, knowledge_basis, document.file_type)
            if document.file_type == 'pdf':
                rule_issues = [issue for issue in rule_issues if issue.get('rule') not in {'R011', 'R016', 'R021'}]
            print(f"[审核] 规则匹配到问题: {len(rule_issues)}个")

            set_progress(review_id, 'running', '术语检查', 35, '正在执行术语检查...')
            terms = get_terms(db)
            print(f"[审核] 加载术语数量: {len(terms)}")
            term_issues = run_term_check(content, terms)
            print(f"[审核] 术语匹配到问题: {len(term_issues)}个")

            if document_language in ("en", "both"):
                set_progress(review_id, 'running', '拼写检查', 45, '正在进行拼写和语法检查...')
                try:
                    spelling_issues = run_spelling_and_grammar_check(content, document.file_type)
                    print(f"[审核] 拼写/语法检查发现问题: {len(spelling_issues)}个")
                    rule_issues.extend(spelling_issues)
                except Exception as e:
                    print(f"[审核] 拼写/语法检查失败: {e}")

                try:
                    heuristic_issues = _run_english_heuristic_audit(content, document.file_type)
                    print(f"[审核] 英文高置信规则发现问题: {len(heuristic_issues)}个")
                    rule_issues.extend(heuristic_issues)
                except Exception as e:
                    print(f"[审核] 英文高置信规则执行失败: {e}")

                if document.file_type == 'pdf':
                    try:
                        structural_issues = _run_pdf_structure_audit(content)
                        print(f"[审核] PDF结构规则发现问题: {len(structural_issues)}个")
                        rule_issues.extend(structural_issues)
                    except Exception as e:
                        print(f"[审核] PDF结构规则执行失败: {e}")

                try:
                    long_sentence_issues = _run_long_sentence_audit(content, document.file_type)
                    print(f"[审核] 长句规则发现问题: {len(long_sentence_issues)}个")
                    rule_issues.extend(long_sentence_issues)
                except Exception as e:
                    print(f"[审核] 长句规则执行失败: {e}")

            candidate_rule_issues = rule_issues + term_issues

            if has_ai_client and len(candidate_rule_issues) > 0:
                set_progress(review_id, 'running', 'AI二次验证', 55, f'正在AI验证 {len(candidate_rule_issues)} 个候选问题...')
                print(f"[审核] 开始AI二次验证，候选问题数={len(candidate_rule_issues)}")
                try:
                    filtered = asyncio.get_event_loop().run_in_executor(None, ai_client.filter_rule_false_positives, candidate_rule_issues, document_language)
                    filtered = asyncio.run(asyncio.wait_for(filtered, timeout=90.0))
                    candidate_rule_issues = filtered
                    print(f"[审核] AI二次验证后保留问题数={len(candidate_rule_issues)}")
                except asyncio.TimeoutError:
                    print(f"[审核] AI 二次验证超时(90s), 使用原始规则结果({len(candidate_rule_issues)}个)")
                except Exception as e:
                    print(f"[审核] AI 二次验证失败, 使用原始规则结果: {e}")

            issues.extend(candidate_rule_issues)
            print(f"[审核] 规则审核阶段共产出问题数={len(candidate_rule_issues)}")

        if mode in ["ai", "hybrid"] and has_ai_client:
            set_progress(review_id, 'running', 'AI智能审核', 65, '正在进行AI深度审核...')
            print(f"[审核] 开始AI智能审核，模式={mode}")
            try:
                ai_result = asyncio.get_event_loop().run_in_executor(None, ai_client.audit_document, content, document_language)
                ai_result = asyncio.run(asyncio.wait_for(ai_result, timeout=180.0))
                ai_issues = ai_result.get("issues", [])
                print(f"[审核] AI审核返回问题数={len(ai_issues)}")
                for issue in ai_issues:
                    issue["source"] = "ai"
                    issue.setdefault("severity", "general")
                    issue.setdefault("category", "其他")
                    issue.setdefault("original_text", "")
                    issue.setdefault("context", "")
                    issue.setdefault("chapter", "")
                    issue.setdefault("rule", "AI")
                    issue.setdefault("suggestion", "")
                    issue.setdefault("description", "")
                    issue.setdefault("audit_basis", "AI 审核")
                    issue.setdefault("confidence", 80)
                    issue.setdefault("position", "")
                    if issue["severity"] not in ("fatal", "serious", "general", "suggestion"):
                        issue["severity"] = "general"
                issues.extend(ai_issues)
            except asyncio.TimeoutError:
                print(f"[审核] AI 审核超时(180s), 跳过 AI 审核")
            except Exception as e:
                print(f"[审核] AI 审核失败, 跳过 AI 审核: {e}")

        set_progress(review_id, 'running', '结果处理', 85, '正在去重和保存结果...')
        issues = dedupe_issues_by_original(issues)
        if document.file_type == 'docx':
            issues = _enrich_docx_issue_positions(document, issues)
        print(f"[审核] 去重后最终问题数={len(issues)}")
        if len(issues) > 0:
            categories = {}
            for issue in issues:
                cat = issue.get("category", "未分类")
                categories[cat] = categories.get(cat, 0) + 1
            print(f"[审核] 问题分类统计: {categories}")

        for issue in issues:
            create_issue(db=db, issue=IssueCreate(
                review_id=review_id,
                severity=issue["severity"],
                category=issue.get("category", ""),
                rule=issue.get("rule", ""),
                chapter=issue.get("chapter", ""),
                original_text=issue.get("original_text", ""),
                context=issue.get("context", ""),
                suggestion=issue.get("suggestion", ""),
                description=issue.get("description", ""),
                audit_basis=issue.get("audit_basis", ""),
                confidence=issue.get("confidence", 0),
                source=issue.get("source", "rule"),
                position=issue.get("position", "")
            ))

        summary = json.dumps({
            "total": len(issues),
            "fatal": len([i for i in issues if i.get("severity") == "fatal"]),
            "serious": len([i for i in issues if i.get("severity") == "serious"]),
            "general": len([i for i in issues if i.get("severity") == "general"]),
            "suggestion": len([i for i in issues if i.get("severity") == "suggestion"]),
            "language": document_language,
        })

        set_progress(review_id, 'completed', '完成', 100, f'审核完成，发现 {len(issues)} 个问题')
        update_review_status(db, review_id, "completed", len(issues), summary)
        print(f"[审核] 任务完成, review_id={review_id}, 问题数={len(issues)}")

    except Exception as e:
        set_progress(review_id, 'failed', '失败', 0, str(e))
        update_review_status(db, review_id, "failed", 0, str(e))
        print(f"[审核] 任务失败, review_id={review_id}, 错误={e}")
    finally:
        db.close()


@router.post("/{document_id}")
async def create_review_task(document_id: int, mode: str = "hybrid", background_tasks: BackgroundTasks = None, db: Session = Depends(get_db)):
    document = get_document(db, document_id=document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    review = create_review(db=db, review=ReviewCreate(document_id=document_id, mode=mode))
    set_progress(review.id, 'running', '初始化', 0, '审核任务已创建')
    
    # 启动后台审核任务
    if background_tasks:
        background_tasks.add_task(_run_review_background, review.id, document_id, mode)
    
    return {"review_id": review.id, "status": "running", "message": "审核任务已启动，请轮询进度"}


@router.get("/{review_id}", response_model=Review)
async def read_review(review_id: int, db: Session = Depends(get_db)):
    review = get_review(db, review_id=review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    doc = get_document(db, document_id=review.document_id)
    review_dict = review.__dict__.copy()
    review_dict['document_name'] = doc.filename if doc else ''
    review_dict['document_file_type'] = doc.file_type if doc else ''
    return review_dict


@router.get("/{review_id}/issues", response_model=list[Issue])
async def read_review_issues(review_id: int, db: Session = Depends(get_db)):
    issues = get_issues(db, review_id=review_id)
    return issues


@router.put("/issues/{issue_id}", response_model=Issue)
async def update_issue_status(issue_id: int, issue_update: IssueUpdate, db: Session = Depends(get_db)):
    issue = update_issue(db, issue_id=issue_id, issue_update=issue_update)
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    return issue


@router.post("/{review_id}/judge")
async def batch_judge_issues(review_id: int, payload: dict, db: Session = Depends(get_db)):
    """批量人工判定问题: { 'judgments': [{'issue_id': 1, 'status': 'confirmed'}, ...] }"""
    judgments = payload.get("judgments", [])
    updated = 0
    for j in judgments:
        issue_id = j.get("issue_id")
        status = j.get("status")
        if not issue_id or not status:
            continue
        # 允许的状态: pending, confirmed, false_positive, ignored
        if status not in ["pending", "confirmed", "false_positive", "ignored"]:
            continue
        from app.schemas.review import IssueUpdate
        issue = update_issue(db, issue_id=issue_id, issue_update=IssueUpdate(status=status))
        if issue:
            updated += 1
    return {"updated": updated, "total": len(judgments)}


@router.get("/{review_id}/export-html")
async def export_review_html(review_id: int, db: Session = Depends(get_db)):
    """导出 HTML 报告 (包含所有问题及人工判定状态)"""
    review = get_review(db, review_id=review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    issues = get_issues(db, review_id=review_id)
    doc = get_document(db, document_id=review.document_id)
    html = _generate_review_html_content(review, doc, issues)
    return HTMLResponse(content=html)


@router.get("/{review_id}/export-result")
async def export_review_result(review_id: int, db: Session = Depends(get_db)):
    review = get_review(db, review_id=review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    document = get_document(db, document_id=review.document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    issues = get_issues(db, review_id=review_id)
    if document.file_type == "docx":
        export_path, export_name, media_type = _export_review_docx(review, document, issues)
    else:
        export_path, export_name, media_type = _export_review_html_file(review, document, issues)

    return FileResponse(path=str(export_path), filename=export_name, media_type=media_type)


@router.get("/{review_id}/report")
async def generate_report(review_id: int, db: Session = Depends(get_db)):
    review = get_review(db, review_id=review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    issues = get_issues(db, review_id=review_id)
    confirmed_issues = [i for i in issues if i.status in ["confirmed", "converted_to_rule"]]

    summary = _load_review_summary(review.summary)

    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>审核报告</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .header {{ text-align: center; margin-bottom: 30px; }}
        .summary {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
        .summary td {{ border: 1px solid #ddd; padding: 8px; }}
        .issue {{ border: 1px solid #ddd; padding: 15px; margin-bottom: 10px; }}
        .fatal {{ border-left: 5px solid #dc3545; }}
        .serious {{ border-left: 5px solid #fd7e14; }}
        .general {{ border-left: 5px solid #ffc107; }}
        .suggestion {{ border-left: 5px solid #17a2b8; }}
    </style>
</head>
<body>
    <div class="header"><h1>智能技术文档审核报告</h1></div>
    <h2>审核概览</h2>
    <table class="summary">
        <tr><td>审核总数</td><td>{summary.get('total', 0)}</td></tr>
        <tr><td>致命问题</td><td>{summary.get('fatal', 0)}</td></tr>
        <tr><td>严重问题</td><td>{summary.get('serious', 0)}</td></tr>
        <tr><td>一般问题</td><td>{summary.get('general', 0)}</td></tr>
        <tr><td>建议</td><td>{summary.get('suggestion', 0)}</td></tr>
    </table>
    <h2>问题详情</h2>
"""

    for issue in confirmed_issues:
        html_content += f"""
    <div class="issue {issue.severity}">
        <h3>问题 #{issue.id}</h3>
        <p><strong>严重级别:</strong> {issue.severity}</p>
        <p><strong>分类:</strong> {issue.category}</p>
        <p><strong>规则:</strong> {issue.rule}</p>
        <p><strong>章节:</strong> {issue.chapter}</p>
        <p><strong>原文:</strong> {issue.original_text}</p>
        <p><strong>上下文:</strong> {issue.context}</p>
        <p><strong>修改建议:</strong> {issue.suggestion}</p>
        <p><strong>问题描述:</strong> {issue.description}</p>
        <p><strong>审核依据:</strong> {issue.audit_basis}</p>
        <p><strong>置信度:</strong> {issue.confidence}%</p>
        <p><strong>来源:</strong> {issue.source}</p>
    </div>
"""

    html_content += "</body></html>"

    return {"content": html_content, "format": "html"}
