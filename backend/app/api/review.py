from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks, File, UploadFile
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
from collections import Counter
from datetime import datetime
from pathlib import Path
from app.database import get_db
from app.crud.document import get_document
from app.crud.review import create_review, get_review, get_reviews, update_review_status, create_issue, get_issues, update_issue
from app.crud.rule import get_rules
from app.crud.term import get_terms
from app.models.term import Term
from app.crud.audit_basis import get_audit_basis
from app.crud.knowledge import get_folder_tree, get_folder, get_folder_files, get_file
from app.schemas.review import Review, Issue, IssueUpdate, ReviewCreate, IssueCreate
from app.rules.reference_integrity_rule import ReferenceIntegrityRule
from app.rules.term_consistency_rule import TermConsistencyRule
from app.utils.ai_client import ai_client
from app.utils.spell_checker import run_spelling_and_grammar_check, is_whitelisted
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


def _mark_review_as_failed(db: Session, review, message: str):
    review = update_review_status(db, review.id, "failed", review.total_issues or 0, message)
    set_progress(review.id, 'failed', '失败', 0, message)
    return review


def _reconcile_review_runtime_state(db: Session, review):
    if not review or review.status != 'running':
        return review

    progress = get_progress(review.id)
    if progress.get('status') == 'running':
        return review

    return _mark_review_as_failed(db, review, '审核任务已中断，请重新发起审核')


def _get_active_review_for_document(db: Session, document_id: int):
    for review in get_reviews(db, document_id=document_id, limit=20):
        review = _reconcile_review_runtime_state(db, review)
        if review and review.status == 'running':
            return review
    return None

router = APIRouter()


def _flatten_folder_tree(nodes):
    for node in nodes or []:
        yield node
        yield from _flatten_folder_tree(node.get("children") or [])


def _get_review_spec_files_from_knowledge(db: Session):
    tree = get_folder_tree(db, None)
    folders = list(_flatten_folder_tree(tree))

    writing_root = next((folder for folder in folders if folder.get("name") == "写作规范"), None)
    if not writing_root:
        return {}

    style_folder = next(
        (folder for folder in folders if folder.get("parent_id") == writing_root.get("id") and folder.get("name") == "写作风格指南"),
        None,
    )
    common_errors_folder = next(
        (folder for folder in folders if folder.get("parent_id") == writing_root.get("id") and folder.get("name") == "常见错误清单"),
        None,
    )

    style_files = get_folder_files(db, style_folder["id"]) if style_folder else []
    common_error_files = get_folder_files(db, common_errors_folder["id"]) if common_errors_folder else []

    result = {}
    for file in style_files:
        name = str(file.get("name") or "")
        if "中文技术文档写作风格指南" in name:
            result["cn_style"] = file
        elif "MGI英文技术文档写作风格指南" in name:
            result["en_style"] = file

    for file in common_error_files:
        name = str(file.get("name") or "")
        if "技术文档常见错误清单与规范" in name:
            result["common_errors"] = file

    return result


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


def _encode_issue_position_with_meta(start=0, end=0, **meta):
    payload = {"start": int(start or 0), "end": int(end or 0)}
    payload.update({key: value for key, value in meta.items() if value not in (None, '')})
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


def _page_number_from_position(content, position):
    start, _ = _parse_issue_position(position)
    if not content:
        return None
    cursor = 0
    for index, page in enumerate(_split_content_pages(content), start=1):
        page_len = len(page)
        if start <= cursor + page_len:
            return index
        cursor += page_len + 1
    return None


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


def _normalize_suggestion_text(suggestion):
    text = str(suggestion or '').strip()
    text = re.sub(r'^建议(?:改为|替换为|统一为|写为|使用|拆成两句：|改为：|使用标准术语:)\s*', '', text)
    text = re.sub(r'^改为\s*', '', text)
    return text.strip()


def validate_suggestion(original: str, suggestion: str) -> bool:
    normalized_suggestion = _normalize_suggestion_text(suggestion)
    if not normalized_suggestion or normalized_suggestion == '-':
        return False
    original_compact = re.sub(r'\s+', ' ', str(original or '')).strip()
    suggestion_compact = re.sub(r'\s+', ' ', normalized_suggestion).strip()
    return original_compact != suggestion_compact


def _sanitize_issue_suggestions(issues):
    for issue in issues:
        suggestion = str(issue.get('suggestion', '') or '')
        if suggestion and not validate_suggestion(issue.get('original_text', ''), suggestion):
            issue['suggestion'] = ''
            issue['confidence'] = max(0, int(issue.get('confidence', 0) or 0) - 10)
    return issues


def _is_spelling_like_issue(issue):
    rule = str(issue.get('rule', '') or '').upper()
    category = str(issue.get('category', '') or '')
    source = str(issue.get('source', '') or '').lower()
    basis = str(issue.get('audit_basis', '') or '')
    text = f'{rule} {category} {source} {basis}'
    return 'SPELL' in text or '拼写' in text or 'spelling' in text.lower()


def _extract_issue_tokens(issue):
    fields = [
        str(issue.get('original_text', '') or ''),
        str(issue.get('description', '') or ''),
        str(issue.get('suggestion', '') or ''),
    ]
    tokens = []
    for field in fields:
        tokens.extend(re.findall(r'[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*', field))
    return tokens


def _should_drop_spelling_issue(issue):
    if not _is_spelling_like_issue(issue):
        return False

    original = str(issue.get('original_text', '') or '').strip()
    context = str(issue.get('context', '') or '').strip()
    description = str(issue.get('description', '') or '').strip()
    suggestion = str(issue.get('suggestion', '') or '').strip()

    if not original and not context:
        return True
    if not original and suggestion and not description:
        return True

    original_tokens = re.findall(r'[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*', original)
    if original_tokens and all(is_whitelisted(token) for token in original_tokens):
        return True

    protected_tokens = [token for token in _extract_issue_tokens(issue) if is_whitelisted(token)]
    suspicious_tokens = [
        token for token in re.findall(r'[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*', original or description)
        if len(token) > 2 and not is_whitelisted(token)
    ]
    return bool(protected_tokens) and not suspicious_tokens


def _should_drop_punctuation_issue(issue):
    rule = str(issue.get('rule', '') or '').upper()
    if rule not in {'PUNCT-001', 'HR003', 'PUNCT-002', 'R002'}:
        return False

    original = str(issue.get('original_text', '') or '').strip()
    context = str(issue.get('context', '') or '')
    if rule == 'R002' and re.search(r'Part\s+No\.?', context, re.IGNORECASE):
        return True
    if original == ':C' and re.search(r'Part\s+No\.?\s*:\s*CSS-\d+', context, re.IGNORECASE):
        return True
    if original == '.R' and re.search(r'Fig(?:ure)?\s*\d+', context, re.IGNORECASE):
        return True
    return False


def _filter_review_false_positives(issues):
    filtered = []
    dropped = 0
    for issue in issues:
        if _should_drop_spelling_issue(issue) or _should_drop_punctuation_issue(issue):
            dropped += 1
            continue
        filtered.append(issue)
    if dropped:
        print(f'[审核] 拼写白名单最终过滤: 过滤 {dropped} 个, 剩余 {len(filtered)} 个')
    return filtered


def _issue_judgment_signature(issue):
    rule = str(_issue_value(issue, 'rule', '') or '').upper()
    original = re.sub(r'\s+', ' ', str(_issue_value(issue, 'original_text', '') or '')).strip().lower()
    category = re.sub(r'\s+', ' ', str(_issue_value(issue, 'category', '') or '')).strip().lower()
    return f'{rule}|{category}|{original}'


def _issue_judgment_signatures(issue):
    rule = str(_issue_value(issue, 'rule', '') or '').upper()
    original = re.sub(r'\s+', ' ', str(_issue_value(issue, 'original_text', '') or '')).strip().lower()
    category = re.sub(r'\s+', ' ', str(_issue_value(issue, 'category', '') or '')).strip().lower()
    if not original:
        return set()
    return {
        f'{rule}|{category}|{original}',
        f'{rule}|{original}',
        f'{category}|{original}',
        original,
    }


def _is_issue_hidden_by_judgment(issue):
    return str(getattr(issue, 'status', '') or '').lower() in {'false_positive', 'ignored'}


def _visible_review_issues(issues):
    return [issue for issue in issues if not _is_issue_hidden_by_judgment(issue)]


def _load_false_positive_signatures_for_document(db: Session, document_id: int):
    signatures = set()
    for review in get_reviews(db, document_id=document_id):
        for issue in get_issues(db, review_id=review.id):
            if str(getattr(issue, 'status', '') or '').lower() == 'false_positive':
                signatures.update(_issue_judgment_signatures(issue))
    return signatures


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
    skip_pattern = re.compile(r'^(?:contents|chapter\s+\d+|figure\s+\d+|table\s+\d+|note:|[-•*]\s+|\d+[\).])', re.IGNORECASE)
    concise_trigger_pattern = re.compile(r'\b(?:before experiment|it is recommended to|in order to|as shown in|intended to guide)\b', re.IGNORECASE)
    imperative_skip_pattern = re.compile(r'^(?:click|select|open|enter|choose|read|take|place|mix|centrifuge|install|log in|log out)\b', re.IGNORECASE)
    action_hint_pattern = re.compile(r'\b(?:double-click|click|clicking|select|open|place|close|add|mix|aspirate|take out|install|log in|log out)\b', re.IGNORECASE)
    ui_step_pattern = re.compile(r'\b(?:figure\s+\d+|table\s+\d+|interface|wizard|button|door|well\b|pos\d+)\b', re.IGNORECASE)
    ui_display_pattern = re.compile(r'\b(?:will appear|will pop up|pop up)\b', re.IGNORECASE)

    for match in sentence_pattern.finditer(content):
        sentence = re.sub(r'\s+', ' ', match.group(0)).strip()
        next_fragment = content[match.end():match.end() + 12].lstrip()
        word_count = len(re.findall(r"[A-Za-z]+(?:[-'][A-Za-z]+)?", sentence))
        if word_count <= 40 or skip_pattern.search(sentence) or '|' in sentence or '\t' in sentence:
            continue
        if not re.search(r'[.!?]$', sentence):
            continue
        if re.search(r'\b[A-Z]\.$', sentence) and next_fragment[:1].islower():
            continue
        if imperative_skip_pattern.search(sentence) and word_count <= 45 and sentence.count(',') <= 1:
            continue
        if action_hint_pattern.search(sentence) and ui_step_pattern.search(sentence) and word_count <= 40:
            continue
        if ui_display_pattern.search(sentence) and ui_step_pattern.search(sentence) and word_count <= 35:
            continue
        normalized = _normalize_search_text(sentence)
        if normalized in seen:
            continue
        seen.add(normalized)
        severity = 'serious' if word_count > 60 else 'general'
        issues.append({
            "severity": severity,
            "category": "句式",
            "rule": "R036",
            "chapter": extract_chapter(content, match.start()),
            "original_text": sentence,
            "context": get_context(content, match.start(), match.end(), 120),
            "suggestion": _build_long_sentence_suggestion(sentence),
            "description": f"单句包含 {word_count} 个词，超过长句阈值，建议拆分或压缩冗余表达。",
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


TOC_BLACKLIST = {
    'ml', 'μl', 'ul', 'l', 'tube', 'well', 'wells',
    'table', 'figure', 'mg', 'ng', 'μg',
    'according to', '×', 'n×', '×50', '|',
}


def _split_pdf_pages(content):
    pages = [page.strip() for page in str(content or '').split('\f')]
    return [page for page in pages if page]


def _extract_toc_title(line):
    title = re.sub(r'\s*\.+\s*\d+\s*$', '', str(line or '')).strip()
    return re.sub(r'\s+', ' ', title)


def _extract_toc_entry(line):
    match = re.match(r'^(?:(\d+(?:\.\d+)*)\s+)?(.+?)\s*\.{2,}\s*(\d+)\s*$', str(line or '').strip())
    if not match:
        return None
    return {
        'section_no': match.group(1) or '',
        'title': re.sub(r'\s+', ' ', match.group(2).strip()),
        'page_no': match.group(3),
    }


def _is_toc_item(line: str) -> bool:
    stripped = str(line or '').strip()
    entry = _extract_toc_entry(stripped)
    if not entry:
        return False

    title_part = entry['title']
    lowered = title_part.lower()
    if any(keyword in lowered for keyword in TOC_BLACKLIST):
        return False
    if len(title_part) > 50:
        return False
    if re.match(r'^[\d\)\(\s]+$', title_part):
        return False
    if re.match(r'^\d+[\)）]\s*$', title_part):
        return False
    return True


def _detect_toc_page_indexes(pages):
    candidate_indexes = []
    for index, page_text in enumerate(pages[:5]):
        lines = [line.strip() for line in page_text.splitlines() if line.strip()]
        toc_like_count = sum(1 for line in lines if _is_toc_item(line))
        has_contents = any(line.lower() == 'contents' for line in lines)
        if has_contents or toc_like_count >= 3:
            candidate_indexes.append(index)
    return candidate_indexes


def _collect_toc_entries(pages):
    toc_entries = {}
    toc_page_indexes = _detect_toc_page_indexes(pages)
    if not toc_page_indexes:
        return toc_entries, set()

    for page_index in toc_page_indexes:
        lines = [line.strip() for line in pages[page_index].splitlines() if line.strip()]
        for line in lines:
            if not _is_toc_item(line):
                continue
            entry = _extract_toc_entry(line)
            if not entry:
                continue
            key = entry['section_no'] or _normalize_heading_text(entry['title'])
            toc_entries[key] = _extract_toc_title(line)
    return toc_entries, set(toc_page_indexes)


def _is_body_heading_line(line):
    stripped = re.sub(r'\s+', ' ', str(line or '').strip())
    if not stripped or len(stripped) > 80:
        return False
    lowered = stripped.lower()
    if any(keyword in lowered for keyword in TOC_BLACKLIST):
        return False
    if '| ' in stripped or ' |' in stripped or '  |  ' in stripped:
        return False
    if '. .' in stripped or re.search(r'\.{2,}\s*\d+$', stripped):
        return False
    if re.search(r'\d+(?:\.\d+)?\s*(?:mL|μL|uL|mg|ng|mm|cm|kg|rpm|min|sec|h)\b', stripped, re.IGNORECASE):
        return False
    if re.match(r'^\d+(?:\.\d+)*\s+[A-Z][A-Za-z0-9 ,/&()_-]{2,}$', stripped):
        return True
    if re.match(r'^(?:Chapter|Section)\s+\d+[\s:.-]+', stripped, re.IGNORECASE):
        return True
    return False


def _run_pdf_structure_audit(content):
    issues = []
    pages = _split_pdf_pages(content)
    if not pages:
        return issues

    toc_entries, toc_page_indexes = _collect_toc_entries(pages)
    body_pages = [page for index, page in enumerate(pages) if index not in toc_page_indexes]
    lines = [line.strip() for page in body_pages for line in page.splitlines() if line.strip()]
    if not lines:
        return issues

    headings = {}
    for line in lines:
        if not _is_body_heading_line(line):
            continue
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
    visible_issues = _visible_review_issues(issues)
    preferred = [i for i in visible_issues if getattr(i, 'status', None) in (None, '', 'pending', 'confirmed', 'converted_to_rule')]
    return sorted(preferred or visible_issues, key=_issue_sort_key)


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


def _format_issue_display_id(index):
    return f"#{index:04d}"


def _highlight_issue_context(issue):
    content = ''
    if isinstance(issue, dict):
        content = issue.get('_document_content', '')
    else:
        content = getattr(issue, '_document_content', '')
    context = _extract_issue_snippet(issue, content)
    original = str(getattr(issue, "original_text", "") or "") if not isinstance(issue, dict) else str(issue.get('original_text', '') or '')
    if not context or context == '-':
        return "-"

    escaped_context = html_lib.escape(context)
    if not original:
        return escaped_context.replace("\n", "<br>")

    escaped_original = html_lib.escape(original)
    pattern = re.compile(re.escape(escaped_original), re.IGNORECASE)
    highlighted = pattern.sub('<span class="problem-highlight">\\g<0></span>', escaped_context, count=1)
    return highlighted.replace("\n", "<br>")


def _split_content_pages(content):
    pages = str(content or '').split('\f')
    return pages if pages else ['']


def _extract_document_metadata(doc, content):
    text = str(content or '')
    pages = _split_content_pages(text)
    normalized = text.replace('\f', '\n')
    metadata = {
        'name': getattr(doc, 'filename', '') or '-',
        'file_type': (getattr(doc, 'file_type', '') or '-').upper(),
        'page_count': len([page for page in pages if page.strip()]) or len(pages),
        'section_count': 0,
        'version': '-',
        'doc_no': '-',
        'language': detect_language(text),
    }

    heading_hits = re.findall(r'(?m)^\s*(?:\d+(?:\.\d+)*[\.)]?\s+[A-Z][^\n]{2,}|(?:Chapter|Section)\s+\d+[^\n]*)', normalized)
    metadata['section_count'] = len(heading_hits)

    patterns = {
        'version': [
            r'\b(?:Version|Rev(?:ision)?|Ver\.?)\s*[:：]?\s*([A-Z]?\d+(?:\.\d+)*)\b',
            r'\bV(?:ersion)?\s*[:：]?\s*([A-Z]?\d+(?:\.\d+)*)\b',
        ],
        'doc_no': [
            r'\bDoc\.?\s*No\.?\s*[:：]?\s*([A-Z0-9\-_/]{4,})\b',
            r'\bDocument\s*(?:No\.?|ID)\s*[:：]?\s*([A-Z0-9\-_/]{4,})\b',
        ],
    }
    for key, exprs in patterns.items():
        for expr in exprs:
            match = re.search(expr, normalized, re.IGNORECASE)
            if match:
                metadata[key] = match.group(1).strip()
                break

    if metadata['doc_no'] == '-' and metadata['name'] and metadata['name'] != '-':
        stem = Path(metadata['name']).stem
        if re.search(r'[A-Z]{1,3}-\d{2,}|\d{3,}', stem):
            metadata['doc_no'] = stem

    return metadata


def _infer_issue_area(issue):
    position_meta = _decode_issue_position(_issue_value(issue, 'position', ''))
    explicit_area = position_meta.get('area')
    if explicit_area:
        return explicit_area

    chapter = str(_issue_value(issue, 'chapter', '') or '')
    context = str(_issue_value(issue, 'context', '') or '')
    original = str(_issue_value(issue, 'original_text', '') or '')
    source = f"{chapter}\n{context}\n{original}".strip()
    line = max(source.splitlines(), key=len, default=source).strip()
    lowered = line.lower()

    if re.search(r'\b(doc\.?\s*no\.?|page\s*\d+|copyright|jb-[a-z0-9\-]+)\b', lowered, re.IGNORECASE):
        return '页脚'
    if re.match(r'^(?:step\s+)?\d+[\.)、：:]\s+', line, re.IGNORECASE):
        return '步骤'
    if re.match(r'^(?:table|表)\s*\d+', line, re.IGNORECASE) or ' | ' in line:
        return '表格'
    if re.match(r'^(?:chapter|section)\s+\d+', line, re.IGNORECASE) or re.match(r'^\d+(?:\.\d+)*\s+[A-Z][^\n]{2,}$', line):
        return '章节'
    return '正文'


def _format_issue_location(issue, content):
    page_no = _page_number_from_position(content, _issue_value(issue, 'position', ''))
    page_text = f'第{page_no}页' if page_no else ''
    chapter = _resolve_issue_heading(issue, content)
    if chapter != '-' and page_text:
        return f'{chapter}（{page_text}）'
    if chapter != '-':
        return chapter
    area = _infer_issue_area(issue)
    if area and page_text:
        return f'{page_text}，{area}'
    return page_text or area or '-'


def _format_issue_chapter(issue):
    area = _infer_issue_area(issue)
    chapter = str(_issue_value(issue, 'chapter', '') or '').strip()
    if area in {'页脚', '步骤'}:
        return '-'
    if not chapter:
        return '-'
    if re.search(r'\b(doc\.?\s*no\.?|page\s*\d+)\b', chapter, re.IGNORECASE):
        return '-'
    if re.match(r'^(?:step\s+)?\d+[\.)、：:]\s+', chapter, re.IGNORECASE):
        return '-'
    compact = re.sub(r'\s+', ' ', chapter).strip()
    compact = re.sub(r'^(#+)\s*', '', compact)
    compact = re.sub(r'^(\d+(?:\.\d+)*)([A-Za-z])', r'\1 \2', compact)
    if re.match(r'^\d+(?:\.\d+)*\s*(?:mL|μL|uL|ng|kg|cm|mm)\b', compact, re.IGNORECASE):
        return '-'
    if _is_inline_reference_heading(compact):
        return '-'
    if re.search(r'\b\d{2,4}\s*[μu]L\b', compact, re.IGNORECASE):
        return '-'
    if _is_table_cell_like(compact):
        return '-'
    if len(compact) > 50:
        return '-'
    return compact


def _extract_heading_from_context(text):
    normalized = re.sub(r'\s+', ' ', str(text or '').replace('\f', ' ')).strip()
    if not normalized:
        return ''
    table_match = re.search(r'(Table\s+\d+\s+[A-Za-z][A-Za-z0-9×\- ,/&()]{3,120})', normalized, re.IGNORECASE)
    if table_match:
        heading = _normalize_heading_text(table_match.group(1))
        if heading and not _is_table_cell_like(heading) and not _is_inline_reference_heading(heading):
            return heading
    patterns = [
        r'(\d+(?:\.\d+)+\s+[A-Z][A-Za-z0-9\- ]{3,80})',
        r'((?:Chapter|Section)\s+\d+[A-Za-z0-9\- :]{3,80})',
    ]
    for pattern in patterns:
        matches = re.findall(pattern, normalized)
        if matches:
            for match in reversed(matches):
                heading = _normalize_heading_text(match)
                if heading and not _is_table_cell_like(heading) and not _is_inline_reference_heading(heading):
                    return heading
    return ''


def _extract_primary_page_heading(content, position):
    page_no = _page_number_from_position(content, position)
    if not page_no:
        return ''
    pages = _split_content_pages(content)
    if page_no < 1 or page_no > len(pages):
        return ''
    page_lines = [line.strip() for line in pages[page_no - 1].splitlines() if line.strip()]
    joined = ' '.join(page_lines)
    table_match = re.search(r'(Table\s+\d+\s+[A-Za-z][A-Za-z0-9×\- ,/&()]{3,120})', joined, re.IGNORECASE)
    if table_match:
        heading = _clean_caption_heading(table_match.group(1))
        if heading and not _is_table_cell_like(heading):
            return heading
    candidates = []
    for index, line in enumerate(page_lines[:80]):
        candidate = _score_heading_candidate(page_lines, index)
        if not candidate:
            continue
        score, heading = candidate
        if _is_table_cell_like(heading):
            continue
        candidates.append((score, heading))
    if not candidates:
        return ''
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _extract_primary_structural_heading(content, position):
    page_no = _page_number_from_position(content, position)
    if not page_no:
        return ''
    pages = _split_content_pages(content)
    if page_no < 1 or page_no > len(pages):
        return ''
    page_lines = [line.strip() for line in pages[page_no - 1].splitlines() if line.strip()]
    candidates = []
    for index, _line in enumerate(page_lines[:120]):
        candidate = _score_heading_candidate(page_lines, index)
        if not candidate:
            continue
        score, heading = candidate
        if _is_table_cell_like(heading) or _is_inline_reference_heading(heading):
            continue
        if not _is_structural_heading_text(heading):
            continue
        candidates.append((score, heading))
    if not candidates:
        return ''
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _extract_previous_page_heading(content, position):
    page_no = _page_number_from_position(content, position)
    if not page_no or page_no <= 1:
        return ''
    pages = _split_content_pages(content)
    for candidate_page in range(page_no - 1, 0, -1):
        page_lines = [line.strip() for line in pages[candidate_page - 1].splitlines() if line.strip()]
        for index in range(len(page_lines) - 1, -1, -1):
            candidate = _score_heading_candidate(page_lines, index)
            if not candidate:
                continue
            score, heading = candidate
            if score < 85:
                continue
            if _is_table_cell_like(heading):
                continue
            return heading
    return ''


def _extract_previous_structural_heading(content, position):
    page_no = _page_number_from_position(content, position)
    if not page_no or page_no <= 1:
        return ''
    pages = _split_content_pages(content)
    for candidate_page in range(page_no - 1, 0, -1):
        page_lines = [line.strip() for line in pages[candidate_page - 1].splitlines() if line.strip()]
        for index in range(len(page_lines) - 1, -1, -1):
            candidate = _score_heading_candidate(page_lines, index)
            if not candidate:
                continue
            score, heading = candidate
            if score < 85:
                continue
            if _is_table_cell_like(heading) or _is_inline_reference_heading(heading):
                continue
            if _is_structural_heading_text(heading):
                return heading
    return ''


def _is_structural_heading_text(text):
    stripped = str(text or '').strip()
    return bool(re.match(r'^(?:\d+(?:\.\d+)*(?:[\).])?|Chapter|Section)\b', stripped, re.IGNORECASE))


def _extract_reference_target(issue):
    fields = [
        str(_issue_value(issue, 'original_text', '') or ''),
        str(_issue_value(issue, 'context', '') or ''),
        str(_issue_value(issue, 'description', '') or ''),
    ]
    combined = ' '.join(fields)
    match = re.search(r'\b(Figure|Fig\.?|Table)\s*(\d+)\b', combined, re.IGNORECASE)
    if not match:
        return '', ''
    label = match.group(1)
    kind = 'Figure' if label.lower().startswith('fig') else 'Table'
    return kind, match.group(2)


def _find_reference_caption(content, issue):
    kind, number = _extract_reference_target(issue)
    if not kind or not number:
        return ''
    page_no = _page_number_from_position(content, _issue_value(issue, 'position', '')) or 1
    pages = _split_content_pages(content)
    page_order = [page_no - 1]
    for distance in range(1, len(pages)):
        prev_index = page_no - 1 - distance
        next_index = page_no - 1 + distance
        if prev_index >= 0:
            page_order.append(prev_index)
        if next_index < len(pages):
            page_order.append(next_index)
    alias = 'Fig\\.?' if kind == 'Figure' else kind
    pattern = re.compile(rf'\b(?:{kind}|{alias})\s*{number}\b[^\n]*', re.IGNORECASE)
    for page_index in page_order:
        page_lines = [line.strip() for line in pages[page_index].splitlines() if line.strip()]
        for line in page_lines:
            if not pattern.search(line):
                continue
            if _is_inline_reference_heading(line) or _is_table_cell_like(line):
                continue
            heading = _clean_caption_heading(line)
            if heading:
                return heading
    return ''


def _issue_prefers_table_caption(issue):
    fields = [
        str(_issue_value(issue, 'original_text', '') or ''),
        str(_issue_value(issue, 'context', '') or ''),
        str(_issue_value(issue, 'description', '') or ''),
    ]
    combined = ' '.join(fields)
    patterns = [
        r'\bLibrary Type\b',
        r'\bcondition\s+condition\b',
        r'\bPos\d',
        r'\boperation deck\b',
        r'\bfilter tips\b',
    ]
    return any(re.search(pattern, combined, re.IGNORECASE) for pattern in patterns)


def _resolve_issue_heading(issue, content):
    chapter = _format_issue_chapter(issue)
    if chapter != '-' and _is_structural_heading_text(chapter):
        return chapter

    position = _issue_value(issue, 'position', '')
    structural_page_heading = _extract_primary_structural_heading(content, position)
    if structural_page_heading and not re.match(r'^(?:\d+(?:\.\d+)*[\).])\s+', structural_page_heading):
        return structural_page_heading

    previous_structural_heading = _extract_previous_structural_heading(content, position)
    if previous_structural_heading:
        return previous_structural_heading

    if structural_page_heading:
        return structural_page_heading

    context_heading = _extract_heading_from_context(_issue_value(issue, 'context', ''))
    if context_heading and _is_structural_heading_text(context_heading):
        return context_heading

    return '-'


def _extract_issue_snippet(issue, content, radius=50):
    original = str(_issue_value(issue, 'original_text', '') or '').strip()
    start, end = _parse_issue_position(_issue_value(issue, 'position', ''))
    if content and original and end > start:
        left = max(0, start - radius)
        right = min(len(content), end + radius)
        snippet = content[left:right].replace('\f', ' ').replace('\n', ' ')
        snippet = re.sub(r'\s+', ' ', snippet).strip()
        if left > 0:
            snippet = '...' + snippet
        if right < len(content):
            snippet = snippet + '...'
        return snippet

    context = str(_issue_value(issue, 'context', '') or '').replace('\n', ' ')
    context = re.sub(r'\s+', ' ', context).strip()
    if not context:
        return original or '-'
    if not original or original not in context:
        return context[:100] + ('...' if len(context) > 100 else '')

    pos = context.find(original)
    left = max(0, pos - radius)
    right = min(len(context), pos + len(original) + radius)
    snippet = context[left:right].strip()
    if left > 0:
        snippet = '...' + snippet
    if right < len(context):
        snippet = snippet + '...'
    return snippet


def _format_issue_description(issue):
    rule = str(_issue_value(issue, 'rule', '') or '')
    original = str(_issue_value(issue, 'original_text', '') or '')
    description = str(_issue_value(issue, 'description', '') or '').strip()

    punct_map = {'，': ',', '。': '.', '；': ';', '：': ':', '（': '(', '）': ')', '、': ','}
    if rule == 'PUNCT-001' and original in punct_map:
        return f'使用了中文全角标点（{original}），应改为英文半角标点（{punct_map[original]}）'

    if rule == 'HR004':
        unit_match = re.match(r'(\d+(?:\.\d+)?)(.+)', original)
        if unit_match:
            return f'数字与单位之间缺少空格，应改为 {unit_match.group(1)} {unit_match.group(2)}'

    return description or '-'


def _format_issue_suggestion(issue):
    rule = str(_issue_value(issue, 'rule', '') or '')
    original = str(_issue_value(issue, 'original_text', '') or '')
    suggestion = str(_issue_value(issue, 'suggestion', '') or '').strip()
    punct_map = {'，': ',', '。': '.', '；': ';', '：': ':', '（': '(', '）': ')', '、': ','}

    if rule == 'PUNCT-001' and original in punct_map:
        return f'{original} → {punct_map[original]}'
    if suggestion.startswith('建议改为 '):
        return suggestion.replace('建议改为 ', '', 1)
    if suggestion.startswith('建议替换为 '):
        return suggestion.replace('建议替换为 ', '', 1)
    return suggestion or '-'


def _issue_dimension(issue):
    rule = str(_issue_value(issue, 'rule', '') or '').upper()
    category = str(_issue_value(issue, 'category', '') or '')
    text = f'{rule} {category}'
    if any(token in text for token in ['SPELL', 'GRAMMAR', 'PUNCT', '时态', '标点', '语法', '拼写', '风格']):
        return '语言质量'
    if any(token in text for token in ['TERM', '术语']):
        return '术语一致性'
    if any(token in text for token in ['LOGIC', '结构', '长句', '步骤连续性', '逻辑完整性']):
        return '逻辑完整性'
    if any(token in text for token in ['SAFE', 'WARNING', 'CAUTION', 'DANGER', '安全', '合规']):
        return '安全合规'
    if any(token in text for token in ['REF', '引用', '交叉']):
        return '交叉引用'
    return '格式规范'


def _build_dimension_summary(issues):
    summary = {name: {'count': 0, 'fatal': 0, 'serious': 0} for name in ['格式规范', '语言质量', '术语一致性', '逻辑完整性', '安全合规', '交叉引用']}
    for issue in issues:
        dimension = _issue_dimension(issue)
        summary[dimension]['count'] += 1
        if _issue_value(issue, 'severity', 'general') == 'fatal':
            summary[dimension]['fatal'] += 1
        if _issue_value(issue, 'severity', 'general') == 'serious':
            summary[dimension]['serious'] += 1
    return summary


def _build_report_conclusion(issues):
    fatal = sum(1 for issue in issues if _issue_value(issue, 'severity', '') == 'fatal')
    serious = sum(1 for issue in issues if _issue_value(issue, 'severity', '') == 'serious')
    if fatal:
        return '当前文档存在高风险问题，建议完成修订并复审后再发布。'
    if serious >= 5:
        return '当前文档可作为修订草稿继续流转，建议先关闭严重问题再进入正式发布。'
    if serious or issues:
        return '当前文档主体可读，建议按优先级关闭剩余问题并做一次快速回归。'
    return '当前文档未发现显著问题，可进入发布前终审。'


def _load_review_spec_texts(db: Session):
    spec_texts = {}
    spec_files = _get_review_spec_files_from_knowledge(db)
    for spec_key, file_info in spec_files.items():
        try:
            path = Path(file_info.get("file_path") or "")
            spec_texts[spec_key] = path.read_text(encoding="utf-8") if path.exists() else ""
        except Exception as exc:
            print(f"[审核] 读取知识库规范文件失败 {file_info.get('file_path')}: {exc}")
            spec_texts[spec_key] = ""
    return spec_texts


def _build_feedback_advice(issues):
    statuses = Counter((getattr(issue, 'status', None) or 'pending') for issue in issues)
    return [
        f"待确认 {statuses.get('pending', 0)} 条，建议审核人优先处理致命和严重问题。",
        f"误报 {statuses.get('false_positive', 0)} 条，建议沉淀为规则白名单或定位策略优化样本。",
        f"已确认 {statuses.get('confirmed', 0)} 条，建议修订后重新执行一次规则审核验证闭环。",
    ]


def _build_problem_summary_rows(issues):
    severity_keys = ['fatal', 'serious', 'general', 'suggestion']
    labels = {'fatal': '致命', 'serious': '严重', 'general': '一般', 'suggestion': '建议'}
    rows = []
    for dimension in ['格式规范', '语言质量', '术语一致性', '逻辑完整性', '安全合规', '交叉引用']:
        items = [issue for issue in issues if _issue_dimension(issue) == dimension]
        if not items:
            continue
        row = {'dimension': dimension, 'total': len(items)}
        for key in severity_keys:
            row[key] = sum(1 for issue in items if _issue_value(issue, 'severity', '') == key)
            row[f'{key}_label'] = labels[key]
        rows.append(row)
    return rows


def _group_issues_by_severity(issues):
    groups = {'fatal': [], 'serious': [], 'general': [], 'suggestion': []}
    for issue in sorted(issues, key=_issue_sort_key):
        groups.setdefault(_issue_value(issue, 'severity', 'general'), []).append(issue)
    return groups


def _build_global_issue_index(groups):
    ordered = []
    for severity in ['fatal', 'serious', 'general', 'suggestion']:
        ordered.extend(groups.get(severity) or [])
    return {id(issue): index for index, issue in enumerate(ordered, start=1)}


def _build_group_heading(severity, entries, index_map):
    labels = {
        'fatal': '致命问题',
        'serious': '严重问题',
        'general': '一般问题',
        'suggestion': '建议项',
    }
    if not entries:
        return labels[severity]
    first_no = index_map[id(entries[0])]
    last_no = index_map[id(entries[-1])]
    if first_no == last_no:
        range_text = _format_issue_display_id(first_no)
    else:
        range_text = f'{_format_issue_display_id(first_no)}-{_format_issue_display_id(last_no)}'
    return f'{labels[severity]}（{range_text}）'


def _build_required_and_recommended_lists(issues):
    required = []
    recommended = []
    for issue in sorted(issues, key=_issue_sort_key):
        item = f"{_format_issue_display_id(0)} {_format_issue_description(issue)}"
        severity = _issue_value(issue, 'severity', '')
        if severity in {'fatal', 'serious'} and len(required) < 5:
            required.append((issue, item))
        elif severity in {'general', 'suggestion'} and len(recommended) < 5:
            recommended.append((issue, item))
    return required, recommended


def _normalize_example_after(issue, before, after):
    if after == '-':
        return after
    rule = str(_issue_value(issue, 'rule', '') or '').upper()
    if rule == 'HR005':
        return 'Well'
    if rule == 'HR004' and re.match(r'\d+(?:\.\d+)?[A-Za-zμ/%]+', before):
        match = re.match(r'(\d+(?:\.\d+)?)([A-Za-zμ/%]+)', before)
        if match:
            return f'{match.group(1)} {match.group(2)}'
    if rule == 'HR001':
        return 'https://global-mgitech.com'
    return after


def _build_diff_markup(before, after):
    before = str(before or '-')
    after = str(after or '-')
    matcher = difflib.SequenceMatcher(None, before, after)
    before_parts = []
    after_parts = []
    for opcode, a0, a1, b0, b1 in matcher.get_opcodes():
        left = html_lib.escape(before[a0:a1])
        right = html_lib.escape(after[b0:b1])
        if opcode == 'equal':
            before_parts.append(left)
            after_parts.append(right)
        else:
            if left:
                before_parts.append(f'<span class="diff-remove">{left}</span>')
            if right:
                after_parts.append(f'<span class="diff-add">{right}</span>')
    return ''.join(before_parts) or '-', ''.join(after_parts) or '-'


def _build_modification_examples(issues):
    target_rules = ['HR005', 'HR004', 'GRAMMAR', 'PUNCT-001', 'HR001']
    examples = []
    used_rules = set()

    def try_add(issue, forced_title=None):
        before = str(_issue_value(issue, 'original_text', '') or '').strip()
        after = _normalize_example_after(issue, before, _format_issue_suggestion(issue))
        if not before or not after or after == '-' or before == after:
            return False
        before_markup, after_markup = _build_diff_markup(before, after)
        examples.append({
            'title': forced_title or _format_issue_description(issue),
            'before': before_markup,
            'after': after_markup,
        })
        used_rules.add(str(_issue_value(issue, 'rule', '') or '').upper())
        return True

    sorted_issues = sorted(issues, key=_issue_sort_key)
    for target in target_rules:
        for issue in sorted_issues:
            rule = str(_issue_value(issue, 'rule', '') or '').upper()
            if target == 'GRAMMAR':
                category = str(_issue_value(issue, 'category', '') or '')
                if '语法' not in category and 'GRAMMAR' not in rule:
                    continue
            elif rule != target:
                continue
            if try_add(issue):
                break

    for issue in sorted_issues:
        if len(examples) >= 5:
            break
        rule = str(_issue_value(issue, 'rule', '') or '').upper()
        if rule in used_rules:
            continue
        try_add(issue)

    return examples


def _build_report_verdict(issues):
    fatal = sum(1 for issue in issues if _issue_value(issue, 'severity', '') == 'fatal')
    serious = sum(1 for issue in issues if _issue_value(issue, 'severity', '') == 'serious')
    if fatal:
        return '不通过'
    if serious >= 3:
        return '需复审'
    if issues:
        return '建议修改'
    return '通过'


def _load_term_variants_from_db(db: Session):
    pairs = []
    for term in db.query(Term).all():
        non_standard = str(getattr(term, 'non_standard', '') or '').strip()
        standard = str(getattr(term, 'standard', '') or '').strip()
        if not non_standard or not standard or non_standard == standard:
            continue
        pairs.append((standard, non_standard))
    return pairs


def _run_db_term_consistency_audit(db: Session, content):
    issues = []
    normalized = str(content or '')
    seen = set()
    for standard, variant in _load_term_variants_from_db(db):
        pattern = re.compile(rf'(?<![A-Za-z0-9]){re.escape(variant)}(?![A-Za-z0-9])', re.IGNORECASE)
        for match in pattern.finditer(normalized):
            key = (variant.lower(), match.start())
            if key in seen:
                continue
            seen.add(key)
            issues.append({
                'severity': 'general',
                'category': '术语一致性',
                'rule': 'TERM-CONSISTENCY-DB',
                'original_text': match.group(0),
                'suggestion': standard,
                'description': f'术语不一致: "{match.group(0)}" 建议统一为 "{standard}"。',
                'audit_basis': '术语库全文术语一致性检查',
                'confidence': 90,
                'source': 'term',
                'position': _encode_issue_position_with_meta(match.start(), match.end(), area='正文'),
                'chapter': extract_chapter(normalized, match.start()),
                'context': get_context(normalized, match.start(), match.end(), 120),
            })
    return issues


def _build_inline_example_html(issue):
    suggestion = html_lib.escape(_format_issue_suggestion(issue))
    before = str(_issue_value(issue, 'original_text', '') or '').strip()
    after = _normalize_example_after(issue, before, _format_issue_suggestion(issue))
    if not suggestion or suggestion == '-':
        return ''
    if not before or not after or before == after or after == '-':
        return (
            '<div class="advice-panel">'
            f'<div class="compare-label">修改建议：<span class="suggestion-inline">{suggestion}</span></div>'
            '</div>'
        )
    before_markup, after_markup = _build_diff_markup(before, after)
    return (
        '<div class="advice-panel">'
        f'<div class="compare-label">修改建议：<span class="suggestion-inline">{suggestion}</span></div>'
        '<div class="comparison-grid">'
        f'<div class="before-box"><span class="box-label">修改前</span>{before_markup}</div>'
        f'<div class="after-box"><span class="box-label">修改后</span>{after_markup}</div>'
        '</div>'
        '</div>'
    )


def _generate_review_html_content(review, doc, issues):
    doc_name = doc.filename if doc else f"文档{review.document_id}"
    content = getattr(doc, 'content', '') if doc else ''
    metadata = _extract_document_metadata(doc, content)
    summary_rows = _build_problem_summary_rows(issues)
    grouped_issues = _group_issues_by_severity(issues)
    issue_index_map = _build_global_issue_index(grouped_issues)
    verdict = _build_report_verdict(issues)
    conclusion = _build_report_conclusion(issues)
    feedback_advice = _build_feedback_advice(issues)
    for issue in issues:
        if isinstance(issue, dict):
            issue['_document_content'] = content
        else:
            setattr(issue, '_document_content', content)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>审核报告 - {doc_name}</title>
    <style>
        * {{ box-sizing: border-box; }}
        :root {{ --ink:#1f2937; --muted:#667085; --line:#dfe5ef; --panel:#ffffff; --bg:#edf2f8; --hero1:#153f70; --hero2:#2f76c9; --fatal:#ef4444; --serious:#f59e0b; --general:#6b7280; --suggestion:#22c55e; --soft:#eff4fb; }}
        body {{ font-family: 'Microsoft YaHei', Arial, sans-serif; margin: 0; padding: 28px; background: radial-gradient(circle at top left, #f8fbff 0, #edf2f8 45%, #e6edf6 100%); color: var(--ink); }}
        .container {{ max-width: 1180px; margin: 0 auto; background: var(--panel); padding: 0 0 32px; box-shadow: 0 18px 50px rgba(18, 39, 69, 0.12); border-radius: 24px; overflow: hidden; }}
        .hero {{ padding: 36px 40px 46px; background: linear-gradient(135deg, var(--hero1), var(--hero2)); color: #fff; }}
        .hero h1 {{ margin: 0 0 10px; font-size: 32px; }}
        .hero p {{ margin: 0; max-width: 760px; color: rgba(255,255,255,0.84); line-height: 1.7; }}
        .section {{ padding: 0 40px; }}
        h2 {{ color: #143b68; margin: 30px 0 16px; font-size: 22px; }}
        .module-tag {{ display: inline-block; margin-top: 12px; padding: 6px 12px; border-radius: 999px; background: rgba(255,255,255,0.16); font-size: 12px; letter-spacing: 0.08em; }}
        .meta {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin: -26px 40px 0; padding: 14px; background: rgba(255,255,255,0.96); border: 1px solid #d8e4f2; border-radius: 22px; box-shadow: 0 14px 36px rgba(18, 39, 69, 0.12); }}
        .meta-card {{ background: linear-gradient(180deg, #ffffff, #f8fbff); border: 1px solid #e2eaf5; border-radius: 16px; padding: 15px 16px; }}
        .meta-label {{ font-size: 12px; color: var(--muted); margin-bottom: 8px; }}
        .meta-value {{ font-weight: 700; line-height: 1.5; }}
        .summary-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 18px 0 10px; }}
        .summary-card {{ padding: 18px 14px; text-align: center; border-radius: 18px; color: #fff; box-shadow: inset 0 1px 0 rgba(255,255,255,0.12); }}
        .summary-card .num {{ font-size: 30px; font-weight: 800; }}
        .summary-card .label {{ font-size: 13px; margin-top: 6px; opacity: 0.92; }}
        .card-fatal {{ background: linear-gradient(135deg, #b91c1c, var(--fatal)); }}
        .card-serious {{ background: linear-gradient(135deg, #d97706, var(--serious)); }}
        .card-general {{ background: linear-gradient(135deg, #4b5563, var(--general)); }}
        .card-suggestion {{ background: linear-gradient(135deg, #15803d, var(--suggestion)); }}
        .callout {{ border: 1px solid #cfe0f5; border-radius: 18px; padding: 18px 20px; background: linear-gradient(180deg, #f8fbff, #f1f6fc); line-height: 1.8; color: #2a4365; }}
        .issue {{ border: 1px solid #e4e7ed; border-radius: 18px; padding: 18px 20px; margin: 12px 0; background: #fff; box-shadow: 0 6px 18px rgba(15, 35, 60, 0.04); }}
        .issue.confirmed {{ border-left: 5px solid #67c23a; background: #f0f9eb; }}
        .issue.false_positive {{ border-left: 5px solid #909399; background: #f4f4f5; opacity: 0.7; }}
        .issue.ignored {{ border-left: 5px solid #c0c4cc; background: #fafafa; opacity: 0.6; }}
        .issue.pending {{ border-left: 5px solid var(--serious); }}
        .issue-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }}
        .issue-title {{ font-weight: bold; color: #303133; }}
        .badge {{ display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 12px; color: #fff; margin-left: 6px; }}
        .badge-confirmed {{ background: #67c23a; }}
        .badge-false {{ background: #909399; }}
        .badge-pending {{ background: var(--serious); }}
        .badge-ignored {{ background: #c0c4cc; }}
        .badge-severity-fatal {{ background: var(--fatal); }}
        .badge-severity-serious {{ background: var(--serious); }}
        .badge-severity-general {{ background: var(--general); }}
        .badge-severity-suggestion {{ background: var(--suggestion); }}
        .issue-field {{ margin: 8px 0; font-size: 14px; }}
        .issue-label {{ font-weight: bold; color: #606266; display: inline-block; min-width: 80px; }}
        .original-text {{ background: #fef0f0; padding: 4px 8px; border-radius: 3px; color: #c45656; font-family: 'Courier New', monospace; }}
        .suggestion {{ background: #f0f9eb; padding: 4px 8px; border-radius: 3px; color: #5a8e3f; }}
        .suggestion-inline {{ color: #14532d; font-weight: 700; }}
        .context {{ color: #444; font-size: 13px; line-height: 1.7; white-space: normal; }}
        .problem-highlight {{ color: #d93025; background: #fff1f0; font-weight: 700; padding: 1px 3px; border-radius: 3px; }}
        .subtle {{ color: #909399; font-size: 12px; }}
        .issue-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
        .empty {{ text-align: center; color: #909399; padding: 40px; }}
        .list-card {{ border: 1px solid var(--line); border-radius: 18px; padding: 18px 20px; background: #fff; margin-bottom: 12px; }}
        .list-card h3 {{ margin: 0 0 10px; font-size: 18px; color: #143b68; }}
        .summary-table-note {{ margin: 12px 0 0; color: var(--muted); font-size: 13px; }}
        table {{ width: 100%; border-collapse: collapse; background: #fff; border-radius: 16px; overflow: hidden; }}
        th, td {{ border: 1px solid #e7edf5; padding: 12px 14px; text-align: left; vertical-align: top; }}
        th {{ background: #f6f9fd; color: #163f6f; }}
        .status-ok {{ color: var(--suggestion); font-weight: 700; }}
        .status-bad {{ color: var(--fatal); font-weight: 700; }}
        .status-warn {{ color: var(--serious); font-weight: 700; }}
        .advice-panel {{ margin-top: 12px; padding: 14px 16px; border: 1px solid #d7e6f7; border-radius: 16px; background: #f8fbff; }}
        .comparison-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 10px; }}
        .before-box, .after-box {{ padding: 12px 14px; border-radius: 14px; line-height: 1.7; }}
        .before-box {{ background: #fffafa; border: 1px solid #f4caca; color: #7f1d1d; }}
        .after-box {{ background: #f6fdf8; border: 1px solid #cdebd6; color: #14532d; }}
        .box-label {{ display: block; color: var(--muted); font-size: 12px; font-weight: 700; margin-bottom: 6px; }}
        .diff-remove {{ background: #fde8e8; text-decoration: line-through; padding: 1px 3px; border-radius: 4px; }}
        .diff-add {{ background: #dcfce7; text-decoration: underline; padding: 1px 3px; border-radius: 4px; }}
        .feedback-block {{ border-top: 1px dashed #cbd5e1; margin-top: 18px; padding-top: 18px; }}
        .compare-label {{ font-weight: 700; color: #163f6f; margin-bottom: 8px; }}
        h3 {{ margin: 22px 0 12px; }}
        .severity-fatal {{ color: var(--fatal); }}
        .severity-serious {{ color: var(--serious); }}
        .severity-general {{ color: var(--general); }}
        .severity-suggestion {{ color: var(--suggestion); }}
        .footer {{ margin: 36px 40px 0; text-align: center; color: #909399; font-size: 12px; border-top: 1px solid #ebeef5; padding-top: 20px; }}
        @media (max-width: 920px) {{ .meta, .summary-grid, .issue-grid, .comparison-grid {{ grid-template-columns: 1fr; }} .section {{ padding: 0 22px; }} .hero {{ padding: 28px 22px 44px; }} .meta {{ margin: -24px 22px 0; padding: 12px; }} .footer {{ margin-left: 22px; margin-right: 22px; }} }}
    </style>
</head>
<body>
    <div class="container">
        <div class="hero">
            <h1>技术文档审核报告</h1>
            <p>本报告基于格式规范、语言质量、术语一致性、逻辑完整性、安全合规、交叉引用六个维度输出结构化审核结果，供编辑修订与复审使用。</p>
            <div class="module-tag">REVIEW TASK #{review.id}</div>
        </div>
        <div class="meta">
            <div class="meta-card"><div class="meta-label">文档名称</div><div class="meta-value">{metadata['name']}</div></div>
            <div class="meta-card"><div class="meta-label">审核日期</div><div class="meta-value">{review.created_at}</div></div>
            <div class="meta-card"><div class="meta-label">审核人</div><div class="meta-value">技术文档审核AI助理</div></div>
            <div class="meta-card"><div class="meta-label">文档范围</div><div class="meta-value">{metadata['file_type']} · {metadata['page_count']} 页 · {metadata['section_count']} 个章节</div></div>
        </div>

        <div class="section">
        <h2>模块 1 · 审核概览</h2>
        <div class="summary-grid">
            <div class="summary-card card-fatal"><div class="num">{sum(1 for issue in issues if _issue_value(issue, 'severity', '') == 'fatal')}</div><div class="label">致命</div></div>
            <div class="summary-card card-serious"><div class="num">{sum(1 for issue in issues if _issue_value(issue, 'severity', '') == 'serious')}</div><div class="label">严重</div></div>
            <div class="summary-card card-general"><div class="num">{sum(1 for issue in issues if _issue_value(issue, 'severity', '') == 'general')}</div><div class="label">一般</div></div>
            <div class="summary-card card-suggestion"><div class="num">{sum(1 for issue in issues if _issue_value(issue, 'severity', '') == 'suggestion')}</div><div class="label">建议</div></div>
        </div>
        </div>
        <div class="section">
        <h2>模块 2 · 问题明细</h2>
        <h3>问题汇总表</h3>
        <table>
            <thead><tr><th>类型</th><th>致命</th><th>严重</th><th>一般</th><th>建议</th><th>总计</th></tr></thead>
            <tbody>
"""

    for row in summary_rows:
        html += f"""
            <tr>
                <td>{row['dimension']}</td>
                <td>{row['fatal']}</td>
                <td>{row['serious']}</td>
                <td>{row['general']}</td>
                <td>{row['suggestion']}</td>
                <td>{row['total']}</td>
            </tr>
"""

    html += """
            </tbody>
        </table>
        <h3>详细问题列表</h3>
"""

    if not issues:
        html += '<div class="empty">未发现任何问题</div>'
    else:
        for severity in ['fatal', 'serious', 'general', 'suggestion']:
            entries = grouped_issues.get(severity) or []
            if not entries:
                continue
            html += f'<h3 class="severity-{severity}">{_build_group_heading(severity, entries, issue_index_map)}</h3>'
            for issue in entries:
                display_no = issue_index_map[id(issue)]
                issue_status = _issue_value(issue, 'status', '') or 'pending'
                sev_class = f"badge-severity-{_issue_value(issue, 'severity', 'general')}"
                status_class = {
                    'confirmed': 'badge-confirmed',
                    'false_positive': 'badge-false',
                    'ignored': 'badge-ignored',
                    'pending': 'badge-pending',
                }.get(issue_status, 'badge-pending')
                status_text = {
                    'confirmed': '已确认',
                    'false_positive': '误报',
                    'ignored': '已忽略',
                    'pending': '待确认',
                }.get(issue_status, '待确认')
                example_html = _build_inline_example_html(issue)
                html += f"""
        <div class="issue {issue_status}">
            <div class="issue-header">
                <div class="issue-title">{_format_issue_display_id(display_no)} · {_issue_dimension(issue)} · {_issue_value(issue, 'category', '') or '未分类'}</div>
                <div>
                    <span class="badge {sev_class}">{_format_issue_severity(_issue_value(issue, 'severity', 'general'))}</span>
                    <span class="badge {status_class}">{status_text}</span>
                </div>
            </div>
            <div class="issue-field"><span class="issue-label">位置:</span> {_format_issue_location(issue, content)}</div>
            <div class="issue-field"><span class="issue-label">原文片段:</span> <span class="context">{_highlight_issue_context(issue)}</span></div>
            <div class="issue-field"><span class="issue-label">问题说明:</span> {html_lib.escape(_format_issue_description(issue))}</div>
            <div class="issue-field"><span class="issue-label">审核依据:</span> {html_lib.escape(_issue_value(issue, 'audit_basis', '-') or '-')}</div>
            {example_html}
        </div>
"""

    html += f"""
        </div>
        <div class="section">
        <h2>模块 3 · 审核结论</h2>
        <div class="callout">
            <div><strong>判定结果:</strong> {html_lib.escape(verdict)}</div>
            <div><strong>结论说明:</strong> {html_lib.escape(conclusion)}</div>
            <div><strong>复审建议:</strong></div>
            <ul>
                <li>{html_lib.escape(feedback_advice[0])}</li>
                <li>{html_lib.escape(feedback_advice[1])}</li>
                <li>{html_lib.escape(feedback_advice[2])}</li>
            </ul>
            <div class="feedback-block">
                <div><strong>审核后反馈：</strong></div>
                <div>1. 本次审核有哪些问题是误报？（请列出编号）</div>
                <div>2. 哪些问题或规则可以记录到 memory 中供后续审核参考？</div>
                <div>3. 其他建议：</div>
            </div>
        </div>
        </div>
"""
    html += f"""
        <div class="footer">由 智能技术文档审核平台 生成 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
    </div>
</body>
</html>"""
    return html


def _run_logic_integrity_audit(content):
    issues = []
    seen = set()
    lines = content.replace('\f', '\n').splitlines()
    previous_step = None
    cursor = 0
    previous_non_empty_line = ''
    for line in lines:
        text = line.strip()
        match = re.match(r'^(?:Step\s+)?(\d+)[\.)]\s+(.+)$', text, re.IGNORECASE)
        if not match:
            if text:
                previous_non_empty_line = text
            cursor += len(line) + 1
            continue
        current = int(match.group(1))
        if re.search(r'\b(?:table|figure|fig\.?|section|chapter)\s*$', previous_non_empty_line, re.IGNORECASE):
            previous_non_empty_line = text
            cursor += len(line) + 1
            continue
        if previous_step is not None and current - previous_step > 1:
            key = ('LOGIC-001', current)
            if key in seen:
                continue
            seen.add(key)
            pos = cursor + line.find(text)
            issues.append({
                'severity': 'serious',
                'category': '逻辑完整性',
                'rule': 'LOGIC-001',
                'chapter': '',
                'original_text': text,
                'context': get_context(content, max(pos, 0), max(pos, 0) + len(text), 120),
                'suggestion': f'建议补齐 Step {previous_step + 1}，或重新编号当前步骤。',
                'description': f'步骤编号从 {previous_step} 跳到 {current}，流程连续性不足。',
                'audit_basis': '操作步骤应保持连续且可追踪。',
                'confidence': 90,
                'source': 'rule',
                'position': _encode_issue_position_with_meta(max(pos, 0), max(pos, 0) + len(text), area='步骤'),
            })
        previous_step = current
        previous_non_empty_line = text
        cursor += len(line) + 1
    return issues


def _run_safety_compliance_audit(content):
    issues = []
    normalized = content.replace('\f', '\n')
    seen = set()

    for match in re.finditer(r'(?im)^\s*(WARNING|CAUTION|DANGER)\b([^\n]*)', normalized):
        label = match.group(1).upper()
        line = match.group(0).strip()
        window = normalized[match.start():match.start() + 120]
        if re.search(r'警告|注意|危险', window):
            continue
        key = ('SAFE-001', match.start())
        if key in seen:
            continue
        seen.add(key)
        issues.append({
                'severity': 'serious',
                'category': '安全合规',
                'rule': 'SAFE-001',
                'chapter': '',
                'original_text': line,
                'context': get_context(normalized, match.start(), match.end(), 120),
                'suggestion': f'{label}: ... → {label} {"警告" if label == "WARNING" else "注意" if label == "CAUTION" else "危险"}: ...',
                'description': f'{label} 缺少对应中文警示语，应补充双语安全提示。',
                'audit_basis': '安全警示应完整传达风险及处置要求。',
                'confidence': 91,
                'source': 'rule',
                'position': _encode_issue_position_with_meta(match.start(), match.end(), area='正文'),
            })

    hazard_pattern = re.compile(r'\b(biohazard|flammable|high voltage|corrosive|laser radiation)\b', re.IGNORECASE)
    for match in hazard_pattern.finditer(normalized):
        window = normalized[max(0, match.start() - 80):min(len(normalized), match.end() + 80)]
        if re.search(r'WARNING|CAUTION|DANGER|警告|注意|危险', window, re.IGNORECASE):
            continue
        key = ('SAFE-002', match.start())
        if key in seen:
            continue
        seen.add(key)
        issues.append({
                'severity': 'fatal',
                'category': '安全合规',
                'rule': 'SAFE-002',
                'chapter': '',
                'original_text': match.group(0),
                'context': get_context(normalized, match.start(), match.end(), 120),
                'suggestion': '建议在该风险描述前增加明确的 WARNING/CAUTION 标题，并说明防护动作。',
                'description': '检测到风险词，附近缺少明确的安全警示标题。',
                'audit_basis': '高风险操作应在正文中显式标注安全等级。',
                'confidence': 93,
                'source': 'rule',
                'position': _encode_issue_position_with_meta(match.start(), match.end(), area='正文'),
            })

    return issues


def _run_cross_reference_audit(content):
    issues = []
    normalized = content.replace('\f', '\n')
    section_numbers = set(re.findall(r'(?m)^\s*(\d+(?:\.\d+)*)[\.)]?\s+[A-Z][^\n]{2,}', normalized))
    step_numbers = {int(num) for num in re.findall(r'(?im)^\s*(?:Step\s+)?(\d+)[\.)]\s+.+$', normalized)}
    table_numbers = set(re.findall(r'(?im)^\s*(?:Table|表)\s*(\d+)\b', normalized))
    figure_numbers = set(re.findall(r'(?im)^\s*(?:Figure|Fig\.|图)\s*(\d+)\b', normalized))
    structured_section_numbers = {num for num in section_numbers if '.' in num}
    seen = set()

    if len(structured_section_numbers) >= 3:
        for match in re.finditer(r'\b(?:Section|Chapter|章节)\s+(\d+(?:\.\d+)*)\b', normalized, re.IGNORECASE):
            ref = match.group(1)
            if ref in section_numbers:
                continue
            key = ('REF-001', ref)
            if key in seen:
                continue
            seen.add(key)
            issues.append({
                    'severity': 'general',
                    'category': '交叉引用',
                    'rule': 'REF-001',
                    'chapter': '',
                    'original_text': match.group(0),
                    'context': get_context(normalized, match.start(), match.end(), 120),
                    'suggestion': f'补充 Section {ref} 对应章节标题，或删除该引用。',
                    'description': f'引用原文：{match.group(0)}；引用类型：章节；目标对象：Section {ref}；检查结果：引用缺失。文档中没有对应章节标题。',
                    'audit_basis': '交叉引用应可回溯到唯一的章节或对象。',
                    'confidence': 88,
                    'source': 'rule',
                    'position': _encode_issue_position_with_meta(match.start(), match.end(), area='正文', reference_type='章节', target=f'Section {ref}', check_result='引用缺失'),
                })

    for match in re.finditer(r'\b(?:according to|refer to|see)?\s*(?:Table|table|表)\s*(\d+)\b', normalized):
        ref = match.group(1)
        if ref in table_numbers:
            continue
        key = ('REF-TABLE', ref, match.start())
        if key in seen:
            continue
        seen.add(key)
        issues.append({
            'severity': 'serious',
            'category': '交叉引用',
            'rule': 'REF-003',
            'chapter': '',
            'original_text': match.group(0).strip(),
            'context': get_context(normalized, match.start(), match.end(), 120),
            'suggestion': f'补充 Table {ref}，或删除该引用。',
            'description': f'引用原文：{match.group(0).strip()}；引用类型：表；目标对象：Table {ref}；检查结果：引用缺失。文档中没有 Table {ref} 的标题。',
            'audit_basis': '表格引用应能定位到唯一的表格标题。',
            'confidence': 92,
            'source': 'rule',
            'position': _encode_issue_position_with_meta(match.start(), match.end(), area='正文', reference_type='表', target=f'Table {ref}', check_result='引用缺失'),
        })

    for match in re.finditer(r'\b(?:Figure|Fig\.|图)\s*(\d+)\b', normalized, re.IGNORECASE):
        ref = match.group(1)
        if ref in figure_numbers:
            continue
        key = ('REF-FIGURE', ref, match.start())
        if key in seen:
            continue
        seen.add(key)
        issues.append({
            'severity': 'general',
            'category': '交叉引用',
            'rule': 'REF-004',
            'chapter': '',
            'original_text': match.group(0),
            'context': get_context(normalized, match.start(), match.end(), 120),
            'suggestion': f'补充 Figure {ref} 对应标题，或删除该引用。',
            'description': f'引用原文：{match.group(0)}；引用类型：图；目标对象：Figure {ref}；检查结果：引用缺失。文档中没有对应图标题。',
            'audit_basis': '图引用应能定位到唯一的图标题。',
            'confidence': 88,
            'source': 'rule',
            'position': _encode_issue_position_with_meta(match.start(), match.end(), area='正文', reference_type='图', target=f'Figure {ref}', check_result='引用缺失'),
        })

    if len(step_numbers) >= 3:
        for match in re.finditer(r'\bStep\s+(\d+)\b', normalized, re.IGNORECASE):
            ref = int(match.group(1))
            if ref in step_numbers:
                continue
            context = get_context(normalized, match.start(), match.end(), 120)
            if re.search(r'\bin\s+section\s+\d+(?:\.\d+)*\b', context, re.IGNORECASE):
                continue
            key = ('REF-002', ref)
            if key in seen:
                continue
            seen.add(key)
            issues.append({
                'severity': 'general',
                'category': '交叉引用',
                'rule': 'REF-002',
                'chapter': '',
                'original_text': match.group(0),
                'context': context,
                'suggestion': f'补充 Step {ref}，或将引用改为有效步骤编号。',
                'description': f'引用原文：{match.group(0)}；引用类型：步骤；目标对象：Step {ref}；检查结果：引用缺失。文档中没有对应步骤。',
                'audit_basis': '步骤引用应和实际流程编号保持一致。',
                'confidence': 88,
                'source': 'rule',
                'position': _encode_issue_position_with_meta(match.start(), match.end(), area='正文', reference_type='步骤', target=f'Step {ref}', check_result='引用缺失'),
            })

    return issues


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

    def looks_like_table_context(context):
        snippet = str(context or '')
        line = max(snippet.splitlines(), key=len, default=snippet)
        compact = re.sub(r'\s+', ' ', line).strip()
        if '\t' in snippet or '|' in snippet:
            return True
        if re.search(r'\b(?:Table|Figure)\s+\d+\b', compact, re.IGNORECASE):
            return True
        if len(re.findall(r'\d+(?:\.\d+)?\s*[A-Za-z%°μ/]+', compact)) >= 2:
            return True
        return bool(re.search(r'\s{3,}', line))

    for match in re.finditer(r"https?://en\.mgi-tech\.com", content, re.IGNORECASE):
        add_issue(match, "HR001", "合规", "建议替换为 https://global-mgitech.com", "海外英文文档中官网地址应使用海外官网域名。", "公司特定规范 - 海外官网地址", "fatal")

    for match in re.finditer(r"\bdesk\s+top\b", content, re.IGNORECASE):
        add_issue(match, "HR002", "英文规范", "建议改为 desktop", "desktop 在该语境中应使用合成词写法。", "英文技术文档写作规范 - 拼写")

    if file_type != "pdf":
        abbreviation_pattern = re.compile(r"(?:\be\.g|\bi\.e|\bDr|\bMr|\bMrs|\bMs|\bProf|\bFig|\bNo)$", re.IGNORECASE)
        for match in re.finditer(r"(?<=[A-Za-z0-9\)])\.(?=[A-Za-z0-9])", content):
            prefix = content[max(0, match.start() - 8):match.start()]
            window = content[max(0, match.start() - 30):min(len(content), match.end() + 30)]
            if abbreviation_pattern.search(prefix):
                continue
            if re.search(r'@|https?://|www\.|\b[A-Za-z0-9-]+\.[A-Za-z]{2,}\b', window):
                continue
            if re.match(r"\d+\.\d+", content[max(0, match.start() - 1):match.end() + 2]):
                continue
            original = content[match.start():min(len(content), match.start() + 2)]
            suggestion = f"建议改为 {original[0]} {original[1:]}" if len(original) == 2 else "建议在句号后补一个空格"
            add_issue_by_span(match.start(), min(len(content), match.start() + len(original)), original, "HR003", "标点符号", suggestion, "英文正文中的句号后应保留空格。", "英文技术文档写作规范 - 标点与空格")

    for match in re.finditer(r"\s+,", content):
        add_issue(match, "PUNCT-002", "标点符号", "建议删除逗号前空格", "逗号前不应有空格。", "英文技术文档写作规范 - 标点与空格")

    unit_pattern = r"(?:ng/μL|ng/uL|μL|uL|mL|mg|ng|g|kg|mm|cm|min|sec|hr|bp)"
    for match in re.finditer(rf"(?<![A-Za-z0-9.])\d+(?:\.\d+)?{unit_pattern}\b", content):
        original = match.group(0)
        unit_match = re.match(r"(\d+(?:\.\d+)?)(.+)", original)
        if not unit_match:
            continue
        suggestion = f"建议改为 {unit_match.group(1)} {unit_match.group(2)}"
        context = get_context(content, match.start(), match.end(), 120)
        severity = 'general' if looks_like_table_context(context) else 'serious'
        add_issue(match, "HR004", "单位", suggestion, "数字与单位之间应保留空格。", "英文技术文档写作规范 - 单位格式", severity)

    for match in re.finditer(r"\b(μL|uL|mL|min|sec|ng|bp)s\b", content):
        unit = match.group(1)
        add_issue(match, "UNIT-002", "单位", f"建议改为 {unit}", "单位符号不使用复数形式。", "英文技术文档写作规范 - 单位格式")

    for match in re.finditer(r"\bWeLL\b", content):
        add_issue(match, "HR005", "格式", "建议统一为 Well", "单词内部大小写形式不一致。", "技术文档常见错误清单 - 格式一致性", "serious")

    range_unit_pattern = r"(?:ng/μL|μL|uL|mL|mg|mm|cm|℃|°C|%)"
    for match in re.finditer(rf"\b\d+(?:\.\d+)?\s*{range_unit_pattern}\s*-\s*\d+(?:\.\d+)?\s*{range_unit_pattern}\b", content):
        text = match.group(0)
        suggestion = re.sub(r"\s*-\s*", " to ", text)
        add_issue(match, "HR006", "格式", f"建议改为 {suggestion}", "英文数值范围建议使用 to 表达范围。", "英文技术文档写作规范 - 范围表达", "serious")

    for match in re.finditer(r"greater than upper limit range", content, re.IGNORECASE):
        add_issue(match, "HR007", "语法", "建议改为 greater than the upper limit range", "该短语前缺少定冠词 the。", "英文技术文档写作规范 - 冠词", "serious")

    for match in re.finditer(r"\b(time|yield|result|sample|concentration)\b([^.!?\n]{0,80})\bhave\s+been\b", content, re.IGNORECASE):
        subject = match.group(1)
        original = match.group(0)
        suggestion = re.sub(r"\bhave\s+been\b", "has been", original, flags=re.IGNORECASE)
        add_issue_by_span(match.start(), match.end(), original, "GRAMMAR-003", "语法", f"建议改为 {suggestion}", f"主语 {subject} 为单数，谓语应使用 has been。", "英语语法规范 - 主谓一致", "serious")

    for match in re.finditer(r"\bmake\s+total\s+volume\b", content, re.IGNORECASE):
        add_issue(match, "GRAMMAR-004", "语法", "建议改为 make a total volume 或 make the total volume", "total volume 前建议添加冠词。", "英语语法规范 - 冠词")

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
        add_issue(match, "HR012", "合规", "建议改为 global-mgitech.com", "海外英文文档中官网域名应统一。", "公司特定规范 - 海外官网地址", "fatal")

    for match in re.finditer(r"\b(?:e-?mail)\s*:", content, re.IGNORECASE):
        if match.group(0).strip() == 'Email:':
            continue
        add_issue(match, "HR013", "格式", "建议统一为 Email:", "联系方式标签建议统一大小写。", "英文技术文档写作规范 - 标签格式")

    for match in re.finditer(r"\b(?:web site|website address)\b", content, re.IGNORECASE):
        add_issue(match, "HR014", "一致性", "建议统一为 website", "网站相关名词建议统一。", "英文技术文档写作规范 - 术语一致性")

    for match in re.finditer(r"\bcharaters\b|\bcharater\b|\boccured\b|\bocurred\b|\btecnical\b|\bseperate\b|\bmaintenence\b|\bmaintanance\b|\breferrence\b|\brefered\b|\brefering\b|\buntill\b|\buseing\b|\bwheras\b|\bwich\b|\bdefination\b|\bdesciption\b|\brecieve\b", content, re.IGNORECASE):
        if is_whitelisted(match.group(0)):
            continue
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
            folder_id = folder.get('id') if isinstance(folder, dict) else getattr(folder, 'id', None)
            folder_name = folder.get('name') if isinstance(folder, dict) else getattr(folder, 'name', '')
            if folder_id is None:
                continue
            folder_obj = get_folder(db, folder_id)
            if folder_obj:
                files = get_folder_files(db, folder_id)
                for file in files:
                    basis_list.append({
                        "title": file.name,
                        "folder": folder_name,
                        "path": f"{folder_name}/{file.name}"
                    })
    except Exception as e:
        print(f"获取知识库审核依据失败: {e}")
    return basis_list


def _is_footer_line(line):
    stripped = str(line or '').strip()
    if not stripped:
        return False
    return bool(re.search(r'\b(doc\.?\s*no\.?|page\s*\d+|copyright|jb-[a-z0-9\-]+)\b', stripped, re.IGNORECASE))


def _is_step_line(line):
    return bool(re.match(r'^(?:step\s+)?\d+(?:\.\d+)*(?:[\.)、：:])\s+', str(line or '').strip(), re.IGNORECASE))


def _is_version_history_line(line):
    stripped = str(line or '').strip()
    return bool(re.search(r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}\s+changes\b', stripped, re.IGNORECASE))


def _is_material_line(line):
    stripped = str(line or '').strip()
    if not stripped:
        return False
    patterns = [
        r'^\d+(?:\.\d+)?\s*(?:mL|μL|uL|L|mg|ng|g|kg|mm|cm)\b',
        r'\bdeep-well plate\b',
        r'\bautomated filter tips\b',
        r'\bskirted PCR plates?\b',
        r'\bNormalized ssCir sample PCR plate\b',
        r'\bPos\d(?:-Pos\d)?\b',
    ]
    return any(re.search(pattern, stripped, re.IGNORECASE) for pattern in patterns)


def _is_table_line(line):
    stripped = str(line or '').strip()
    return bool(' | ' in stripped or re.match(r'^(?:Table|表)\s*\d+', stripped, re.IGNORECASE))


def _is_figure_or_table_caption(line):
    stripped = str(line or '').strip()
    return bool(re.match(r'^(?:Figure|Fig\.?|Table|表|图)\s*\d+\b', stripped, re.IGNORECASE))


def _is_heading_line(line):
    stripped = str(line or '').strip()
    if not stripped or _is_footer_line(stripped) or _is_step_line(stripped) or _is_table_line(stripped) or _is_material_line(stripped) or _is_version_history_line(stripped):
        return False
    if stripped.startswith('#'):
        return True
    if re.match(r'^(?:Chapter|Section)\s+\d+[\s:.-]+', stripped, re.IGNORECASE):
        return True
    return bool(re.match(r'^\d+(?:\.\d+)*(?:[\).])?\s+[^\n]{2,}$', stripped))


def _normalize_heading_text(line):
    cleaned = re.sub(r'^(\d+(?:\.\d+)*)([A-Za-z])', r'\1 \2', str(line or '').strip())
    return re.sub(r'\s+', ' ', cleaned).strip(' -:|')


def _clean_caption_heading(line):
    heading = _normalize_heading_text(line)
    if not heading:
        return ''
    heading = re.sub(r'\b(Name|Position|Brand|Cat\.?|Cat No\.?|Quantity|Components)\b.*$', '', heading, flags=re.IGNORECASE).strip(' -:|,')
    heading = re.sub(r'\s+', ' ', heading).strip()
    return heading or _normalize_heading_text(line)


def _is_inline_reference_heading(text):
    normalized = _normalize_heading_text(text).lower()
    if not normalized:
        return False
    patterns = [
        r'\btable\s+\d+\s+and\s+figure\s+\d+\b',
        r'\bfigure\s+\d+\s+and\s+table\s+\d+\b',
        r'\baccording\s+to\b',
        r'\bas\s+shown\s+in\b',
        r'\bwill\s+be\b',
        r'\bplace\s+it\b',
    ]
    return any(re.search(pattern, normalized, re.IGNORECASE) for pattern in patterns)


def _looks_like_standalone_heading(lines, index):
    current = str(lines[index] or '').strip()
    if not current:
        return False
    if not re.match(r'^[A-Z][A-Za-z0-9\s\-_/]{3,60}$', current):
        return False
    prev_line = str(lines[index - 1] or '').strip() if index - 1 >= 0 else ''
    next_line = str(lines[index + 1] or '').strip() if index + 1 < len(lines) else ''
    if _is_table_cell_like(current) or _is_table_cell_like(prev_line) or _is_table_cell_like(next_line):
        return False
    if prev_line and next_line and not _is_heading_line(prev_line) and not _is_heading_line(next_line):
        return False
    return True


def _is_table_cell_like(line):
    stripped = str(line or '').strip()
    if not stripped:
        return False
    if _is_version_history_line(stripped):
        return True
    if _is_material_line(stripped):
        return True
    if '|' in stripped:
        return True
    if re.search(r'\b(?:Cat\.?\s*No\.?|Recommended brand|Quantity|Components|Library Type|types|condition|None)\b', stripped, re.IGNORECASE):
        return True
    if re.search(r'\b(?:Vortex mixer|Mini centrifuge|Primer hybridization)\b', stripped, re.IGNORECASE):
        return True
    if re.search(r'\bautomated filter tips\b|\bPos\d(?:-Pos\d)?\b', stripped, re.IGNORECASE):
        return True
    if re.search(r'\d+(?:\.\d+)?\s*mL/tube', stripped, re.IGNORECASE):
        return True
    if re.search(r'\b\d{2,4}\s*[μu]L\b', stripped, re.IGNORECASE):
        return True
    return False


def _is_isolated_heading(lines, index):
    prev_line = str(lines[index - 1] or '').strip() if index - 1 >= 0 else ''
    next_line = str(lines[index + 1] or '').strip() if index + 1 < len(lines) else ''
    return (not prev_line) or (not next_line)


def _score_heading_candidate(lines, index):
    line = str(lines[index] or '').strip()
    if not line:
        return None
    if _is_footer_line(line) or _is_step_line(line) or _is_material_line(line) or _is_version_history_line(line):
        return None
    score = None
    kind = None
    if line.startswith('#'):
        score = 120
        kind = 'markdown'
    elif _is_heading_line(line):
        score = 100
        kind = 'numbered'
    elif _is_figure_or_table_caption(line):
        score = 88
        kind = 'caption'
    elif _looks_like_standalone_heading(lines, index):
        score = 60
        kind = 'standalone'
    if score is None:
        return None

    if _is_inline_reference_heading(line):
        return None
    if _is_table_cell_like(line):
        score -= 45
    if kind == 'standalone' and not _is_isolated_heading(lines, index):
        score -= 20
    if len(line) > 70:
        score -= 10
    if len(line.split()) <= 2 and kind == 'standalone':
        score -= 10
    if score < 55:
        return None

    heading = _clean_caption_heading(line) if kind == 'caption' else _normalize_heading_text(line)
    return score, heading


def extract_chapter(content, position):
    normalized = str(content or '').replace('\f', '\n')
    safe_position = max(0, min(int(position or 0), len(normalized)))
    before_lines = normalized[:safe_position].split('\n')
    after_lines = normalized[safe_position:].split('\n')[:12]
    candidates = []

    start_index = max(0, len(before_lines) - 220)
    for index in range(len(before_lines) - 1, start_index - 1, -1):
        candidate = _score_heading_candidate(before_lines, index)
        if candidate:
            score, text = candidate
            distance_penalty = min(len(before_lines) - 1 - index, 30)
            candidates.append((score - distance_penalty, text))

    for index, _line in enumerate(after_lines[:10]):
        candidate = _score_heading_candidate(after_lines, index)
        if candidate:
            score, text = candidate
            if _is_table_cell_like(text):
                continue
            candidates.append((score - 24 - index, text))

    if candidates:
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]
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
        review = _reconcile_review_runtime_state(db, review)
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
async def get_review_progress(review_id: int, db: Session = Depends(get_db)):
    review = get_review(db, review_id=review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    review = _reconcile_review_runtime_state(db, review)
    if review.status == 'running':
        return get_progress(review_id)

    return {
        'status': review.status,
        'step': '完成' if review.status == 'completed' else '失败',
        'progress': 100 if review.status == 'completed' else 0,
        'message': review.summary or ('审核完成' if review.status == 'completed' else '审核失败'),
        'timestamp': datetime.now().isoformat(),
    }


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
        lowered_context = context.lower()
        if "/" in context or "rpm/min" in lowered_context:
            return True
        if re.search(r'\b(?:min|sec|hr)\b', original_text, re.IGNORECASE):
            return True

    if rule_no == "R013":
        if re.fullmatch(r'\d+[xX]', original_text):
            return True
        if re.search(r'\b\d+[xX]\b', original_text):
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


def _run_reference_and_term_consistency_audit(db: Session, content):
    issues = []

    try:
        issues.extend(ReferenceIntegrityRule().check(content))
    except Exception as e:
        print(f"[审核] 引用完整性规则执行失败: {e}")

    try:
        for issue in TermConsistencyRule().check(content):
            start, end = _parse_issue_position(issue.get('position', ''))
            issue.setdefault('chapter', extract_chapter(content, start))
            issue.setdefault('context', get_context(content, start, end or start + len(issue.get('original_text', '')), 120))
            normalized = str(issue.get('suggestion', '') or '').strip()
            if normalized and not normalized.startswith('建议'):
                issue['suggestion'] = f'建议统一为 {normalized}'
            issues.append(issue)
    except Exception as e:
        print(f"[审核] 术语一致性规则执行失败: {e}")

    try:
        issues.extend(_run_db_term_consistency_audit(db, content))
    except Exception as e:
        print(f"[审核] 术语库一致性规则执行失败: {e}")

    return issues


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
        spec_texts = _load_review_spec_texts(db)
        false_positive_signatures = _load_false_positive_signatures_for_document(db, document_id)
        print(f"[审核] 文档ID={document_id}, 语言检测={document_language}, 内容长度={len(content)}字符")
        print(
            "[审核] 当前规范文件长度: "
            f"cn={len(spec_texts.get('cn_style', ''))}, "
            f"en={len(spec_texts.get('en_style', ''))}, "
            f"common={len(spec_texts.get('common_errors', ''))}"
        )

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
                    supplemental_issues = _run_reference_and_term_consistency_audit(db, content)
                    print(f"[审核] 引用/术语规则发现问题: {len(supplemental_issues)}个")
                    rule_issues.extend(supplemental_issues)
                except Exception as e:
                    print(f"[审核] 引用/术语规则执行失败: {e}")

                try:
                    logic_issues = _run_logic_integrity_audit(content)
                    print(f"[审核] 逻辑完整性规则发现问题: {len(logic_issues)}个")
                    rule_issues.extend(logic_issues)
                except Exception as e:
                    print(f"[审核] 逻辑完整性规则执行失败: {e}")

                try:
                    safety_issues = _run_safety_compliance_audit(content)
                    print(f"[审核] 安全合规规则发现问题: {len(safety_issues)}个")
                    rule_issues.extend(safety_issues)
                except Exception as e:
                    print(f"[审核] 安全合规规则执行失败: {e}")

                try:
                    cross_ref_issues = _run_cross_reference_audit(content)
                    print(f"[审核] 交叉引用规则发现问题: {len(cross_ref_issues)}个")
                    rule_issues.extend(cross_ref_issues)
                except Exception as e:
                    print(f"[审核] 交叉引用规则执行失败: {e}")

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
        issues = _sanitize_issue_suggestions(issues)
        issues = _filter_review_false_positives(issues)
        if false_positive_signatures:
            before_count = len(issues)
            issues = [issue for issue in issues if not (_issue_judgment_signatures(issue) & false_positive_signatures)]
            print(f"[审核] 历史误报过滤: 过滤 {before_count - len(issues)} 个, 剩余 {len(issues)} 个")
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
    if mode not in {"rule", "ai", "hybrid"}:
        raise HTTPException(status_code=400, detail="Unsupported review mode")

    document = get_document(db, document_id=document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    active_review = _get_active_review_for_document(db, document_id)
    if active_review:
        set_progress(active_review.id, 'running', '初始化', 0, '已有审核任务正在执行')
        return {"review_id": active_review.id, "status": "running", "message": "已有审核任务正在执行，请轮询进度"}

    review = create_review(db=db, review=ReviewCreate(document_id=document_id, mode=mode))
    update_review_status(db, review.id, "running", 0, "审核任务已创建")
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
    review = _reconcile_review_runtime_state(db, review)
    doc = get_document(db, document_id=review.document_id)
    review_dict = review.__dict__.copy()
    review_dict['document_name'] = doc.filename if doc else ''
    review_dict['document_file_type'] = doc.file_type if doc else ''
    return review_dict


@router.get("/{review_id}/issues", response_model=list[Issue])
async def read_review_issues(review_id: int, db: Session = Depends(get_db)):
    issues = get_issues(db, review_id=review_id)
    return _visible_review_issues(issues)


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

    issues = _visible_review_issues(get_issues(db, review_id=review_id))
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

    issues = _visible_review_issues(get_issues(db, review_id=review_id))
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

    issues = _visible_review_issues(get_issues(db, review_id=review_id))
    confirmed_issues = [i for i in issues if i.status in ["confirmed", "converted_to_rule"]]

    html_content = _generate_review_html_content(review, get_document(db, document_id=review.document_id), confirmed_issues)
    return {"content": html_content, "format": "html"}
