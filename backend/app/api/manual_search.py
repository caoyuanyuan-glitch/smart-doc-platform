import os
import re
import json
import uuid
import shutil
import base64
import fitz
import time
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, List
from datetime import timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse, FileResponse, Response
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.api.auth import get_current_active_user
from app.database import get_db
from app.models.qa_history import QaSession, QaMessage
from app.api.auth import oauth2_scheme
from app.api.qa import (
    _tokenize, _char_ngrams, _normalize_text,
    _split_content_to_chunks, _score_chunk,
    _get_user_id_from_token, _save_qa_history, _to_beijing_iso, _elapsed_ms,
)
from app.utils.ai_client import ai_client, detect_source_lang
from app.utils.official_manual import (
    cache_file_id,
    download_official_pdf,
    extract_search_keyword,
    extract_search_keywords,
    filter_manuals_by_keywords,
    filter_manuals_by_lang,
    has_cached_en_pdf,
    OfficialSearchError,
    needs_user_choice_for_keywords,
    normalize_site,
    pick_from_candidates,
    public_item,
    rank_manuals_for_keywords,
    search_official_manuals_for_keywords,
    select_manuals_for_keywords,
)

router = APIRouter(dependencies=[Depends(get_current_active_user)])


def _offline_pdf_unavailable(picked: List[dict], user_key: str) -> bool:
    """缓存的英文索引命中了手册，但本地没有对应 PDF 且未解析过。"""
    uploads = UPLOAD_SESSIONS.get(user_key, {})
    for item in picked:
        if not item.get("_cached"):
            continue
        record = uploads.get(cache_file_id(item))
        if record and record.get("pages"):
            continue
        files = item.get("files") or ""
        if "global-mgitech.com" in files and not has_cached_en_pdf(files):
            return True
    return False

logger = logging.getLogger(__name__)
BEIJING_TZ = timezone(timedelta(hours=8))
TEMP_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "manual_uploads")
os.makedirs(TEMP_DIR, exist_ok=True)
OFFICIAL_DIR = os.path.join(TEMP_DIR, "official")
os.makedirs(OFFICIAL_DIR, exist_ok=True)

UPLOAD_SESSIONS = {}


class StartSessionInput(BaseModel):
    file_ids: List[str]


class AskInput(BaseModel):
    session_id: int
    question: str


class QueryInput(BaseModel):
    question: str
    product: str = ""
    session_id: Optional[int] = None
    official_ids: Optional[List[int]] = None
    file_ids: Optional[List[str]] = None
    site: str = "zh"


def _session_title(question: str, product: str = "") -> str:
    q = re.sub(r"\s+", " ", (question or "").strip())
    models = []
    if (product or "").strip():
        models = extract_search_keywords("", product)
    prefix = [m for m in models if m and m.lower() not in q.lower()]
    if prefix:
        q = "、".join(prefix) + " " + q
    return q[:80]


def _extract_pdf_pages(file_path: str) -> Optional[List[dict]]:
    pages = _extract_with_fitz(file_path)
    if pages and _has_meaningful_chinese(pages):
        return pages
    plumber_pages = _extract_with_pdfplumber(file_path)
    if plumber_pages:
        return plumber_pages
    return pages


def _has_meaningful_chinese(pages: List[dict]) -> bool:
    cn = 0
    for p in pages:
        for ch in p.get("text", ""):
            if '\u4e00' <= ch <= '\u9fff':
                cn += 1
                if cn >= 10:
                    return True
    return cn >= 10


def _extract_with_fitz(file_path: str) -> Optional[List[dict]]:
    try:
        doc = fitz.open(file_path)
        pages = []
        for i, page in enumerate(doc):
            text = page.get_text()
            if text and text.strip():
                pages.append({"page_num": i + 1, "text": text.strip()})
        doc.close()
        return pages if pages else None
    except Exception:
        return None


def _extract_with_pdfplumber(file_path: str) -> Optional[List[dict]]:
    try:
        import pdfplumber
        pages = []
        with pdfplumber.open(file_path) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text()
                if text and text.strip():
                    pages.append({"page_num": i + 1, "text": text.strip()})
        return pages if pages else None
    except Exception:
        return None


def _split_pages_to_chunks(pages: List[dict], chunk_size: int = 600, overlap: int = 150) -> List[dict]:
    chunks = []
    step = max(chunk_size - overlap, 80)
    for page in pages:
        text = _normalize_text(page["text"])
        if len(text) <= chunk_size:
            chunks.append({"text": text, "page_num": page["page_num"]})
            continue
        start = 0
        idx = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunk_text = text[start:end]
            if chunk_text.strip():
                chunks.append({"text": chunk_text, "page_num": page["page_num"], "chunk_idx": idx})
            start += step
            idx += 1
    return chunks


def _score_chunk_with_page(question: str, chunk: dict, title: str) -> float:
    score = _score_chunk(question, chunk["text"], title)
    return score


def _is_procedure_question(question: str) -> bool:
    return bool(re.search(r"(如何|怎么|步骤|准备|操作|流程|开机)", question or ""))


def _has_numbered_steps(text: str) -> bool:
    return len(re.findall(r"(?:^|\n)\s*(?:\d+\s*[\.、]|步骤\s*\d+)", text or "")) >= 3


def _has_procedure_body(text: str) -> bool:
    if _has_numbered_steps(text):
        return True
    bullets = re.findall(r"(?:^|\n)\s*[-*]\s+\S{8,}", text or "")
    return len(bullets) >= 3


def _needs_earlier_steps(text: str) -> bool:
    if not re.search(r"根据步骤\s*\d+", text or ""):
        return False
    return not _has_numbered_steps(text)


def _page_refs_in_text(text: str) -> list:
    return [int(num) for num in re.findall(r"第\s*(\d+)\s*页", text or "")]


def _looks_like_toc(text: str) -> bool:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    if len(lines) < 3:
        return False
    toc_like = 0
    for line in lines:
        if re.search(r"\.{2,}\s*\d{1,3}\s*$", line):
            toc_like += 1
        elif re.search(r"[\u4e00-\u9fff].{0,60}\s+\d{1,3}\s*$", line) and not re.search(r"(第\s*\d+\s*页)", line):
            toc_like += 1
    return toc_like >= 3


_QUESTION_PREFIX_RE = re.compile(r"^(如何|怎么|怎样|请|请问)+")
_QUESTION_SUFFIX_RE = re.compile(r"(的操作步骤|操作步骤|的步骤|步骤|怎么做|如何做|吗|呢)+$")


def _question_topic(question: str) -> str:
    text = _normalize_text(question)
    text = _QUESTION_PREFIX_RE.sub("", text)
    text = _QUESTION_SUFFIX_RE.sub("", text)
    return text.strip()


def _compact_zh(text: str) -> str:
    return re.sub(r"[\s\d\.、。；;:：•●○■□（）()]+", "", text or "")


def _topic_in_text(topic: str, text: str) -> bool:
    topic = (topic or "").strip()
    text = text or ""
    if len(topic) < 4 or not text:
        return False
    if topic in text:
        return True
    compact_topic = _compact_zh(topic)
    compact_text = _compact_zh(text)
    if compact_topic and compact_topic in compact_text:
        return True
    if len(compact_topic) >= 6:
        prefix, rest = compact_topic[:2], compact_topic[2:]
        if rest and re.search(re.escape(prefix) + r".{0,12}" + re.escape(rest), compact_text):
            return True
    return False


def _heading_match_boost(question: str, text: str) -> float:
    topic = _question_topic(question)
    if len(topic) < 4:
        return 0.0
    boost = 0.0
    compact_topic = _compact_zh(topic)
    for raw in (text or "").splitlines()[:40]:
        line = raw.strip().lstrip("#").strip()
        if not line or len(line) > 48:
            continue
        compact_line = _compact_zh(re.sub(r"^[\d\.\s、章节第部分]+", "", line))
        if not compact_line:
            continue
        if compact_line == compact_topic:
            return 12.0
        if _topic_in_text(topic, line) and abs(len(compact_line) - len(compact_topic)) <= 10:
            boost = max(boost, 8.0)
        elif compact_line in compact_topic and len(compact_line) >= 6:
            boost = max(boost, 5.0)
    if _topic_in_text(topic, text):
        boost = max(boost, 6.0)
    return boost


def _competing_chapter_penalty(question: str, text: str) -> float:
    topic = _question_topic(question)
    if "准备" not in topic:
        return 0.0
    if _topic_in_text(topic, text):
        return 0.0
    head = "\n".join((text or "").splitlines()[:10])
    if re.search(r"(手动清洗|维护清洗|清洗测序试剂槽|清洗试剂槽)", head):
        return -8.0
    return 0.0


def _heading_page_refs(text: str, question: str) -> list:
    tokens = [t for t in _tokenize(question) if len(t) >= 2]
    topic = _question_topic(question)
    if not tokens and len(topic) < 4:
        return []
    pages = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        match = re.search(r"(?:\.{2,}|\s)(\d{1,3})\s*$", stripped)
        if not match:
            continue
        hits = sum(1 for token in tokens if token in stripped)
        if topic and len(topic) >= 4 and topic in stripped:
            hits = max(hits, 2)
        if hits >= 2:
            pages.append(int(match.group(1)))
    return pages


def _document_page_map(documents: List[dict]) -> dict:
    mapping = {}
    for doc in documents:
        title = doc.get("title", "")
        mapping[title] = {
            int(page.get("page_num") or 0): page.get("text") or ""
            for page in (doc.get("pages") or [])
            if int(page.get("page_num") or 0) > 0
        }
    return mapping


def _expand_ranked_with_neighbors(
    ranked: List[dict],
    documents: List[dict],
    question: str = "",
    before: int = 2,
    after: int = 1,
    limit: int = 16,
) -> List[dict]:
    page_map = _document_page_map(documents)
    seen = set()
    expanded = []

    def add_page(title, page_num, score):
        key = (title, page_num)
        if key in seen:
            return
        raw = (page_map.get(title) or {}).get(page_num)
        if not raw:
            return
        seen.add(key)
        expanded.append({
            "title": title,
            "chunk": _normalize_text(raw),
            "page_num": page_num,
            "score": score,
        })

    for item in ranked:
        title = item.get("title", "")
        page = int(item.get("page_num") or 0)
        if page <= 0:
            continue
        chunk = item.get("chunk") or ""
        if _competing_chapter_penalty(question, chunk) < 0:
            continue
        extra_before = 4 if _needs_earlier_steps(chunk) else before
        score = item.get("score", 0) or 0
        for neighbor in range(max(1, page - extra_before), page + after + 1):
            add_page(title, neighbor, score - abs(neighbor - page) * 0.01)
        jump_pages = _page_refs_in_text(chunk) + _heading_page_refs(chunk, question)
        for ref in jump_pages:
            add_page(title, ref, score + 0.3)
            for neighbor in range(max(1, ref), ref + 3):
                add_page(title, neighbor, score)
        if _is_procedure_question(question) or _needs_earlier_steps(chunk):
            tokens = [t for t in _tokenize(question) + _tokenize(chunk) if len(t) >= 2]
            topic = _question_topic(question)
            related = []
            for page_num, text in (page_map.get(title) or {}).items():
                if (title, page_num) in seen or not _has_procedure_body(text):
                    continue
                if _competing_chapter_penalty(question, text) < 0:
                    continue
                if not _needs_earlier_steps(chunk) and topic and len(topic) >= 4 and not _topic_in_text(topic, text):
                    continue
                hits = sum(1 for token in tokens if token in text)
                if hits >= 2:
                    related.append((hits, page_num))
            related.sort(reverse=True)
            for _, page_num in related[:6]:
                add_page(title, page_num, score - 0.02)

    return expanded[:limit] if expanded else ranked


def _order_context_sources(sources: List[dict]) -> List[dict]:
    title_order = []
    grouped = {}
    for item in sources:
        title = item.get("title", "")
        if title not in grouped:
            title_order.append(title)
            grouped[title] = []
        grouped[title].append(item)
    ordered = []
    for title in title_order:
        pages = grouped[title]
        pages.sort(key=lambda x: int(x.get("page_num") or 0))
        ordered.extend(pages)
    return ordered


def _rank_page_chunks(question: str, documents: List[dict], limit: int = 10) -> List[dict]:
    procedure = _is_procedure_question(question)
    per_doc = []
    for doc in documents:
        chunks = _split_pages_to_chunks(doc.get("pages", []))
        scored = []
        for ch in chunks:
            score = _score_chunk(question, ch["text"], doc.get("title", ""))
            score += _heading_match_boost(question, ch["text"])
            score += _competing_chapter_penalty(question, ch["text"])
            if procedure:
                if _looks_like_toc(ch["text"]):
                    score -= 2.0
                elif _has_procedure_body(ch["text"]):
                    score += 1.2
            scored.append({
                "title": doc.get("title", "未知"),
                "chunk": ch["text"],
                "page_num": ch["page_num"],
                "score": score,
            })
        scored.sort(key=lambda x: x["score"], reverse=True)
        per_doc.append(scored)
    if len(per_doc) > 1:
        take = max(3, limit // max(len(per_doc), 1))
        mixed = []
        for scored in per_doc:
            mixed.extend(scored[:take])
        mixed.sort(key=lambda x: x["score"], reverse=True)
        return mixed[: max(limit, take * len(per_doc))]
    all_chunks = per_doc[0] if per_doc else []
    return all_chunks[:limit]


def _build_context(sources: List[dict], max_chars: int = 10000) -> str:
    parts = []
    total = 0
    for i, s in enumerate(sources):
        block = f"【来源 {i+1}】文档「{s['title']}」第 {s['page_num']} 页\n{s['chunk']}"
        if total + len(block) > max_chars:
            break
        parts.append(block)
        total += len(block)
    return "\n\n---\n\n".join(parts)


def _is_valid_answer(text):
    if not text or len(text.strip()) < 20:
        return False
    short_patterns = ["OK", "ok", "好的", "收到", "明白", "已处理"]
    stripped = text.strip().strip('"')
    if stripped in short_patterns:
        return False
    return True


def _call_ai_with_citations(question: str, context: str, titles: List[str]) -> dict:
    if not context.strip():
        return {"answer": "当前已选文档中未检索到相关内容。", "source": ""}

    title_str = "、".join(titles) if titles else "说明书"
    source_lang = detect_source_lang(context, titles)

    try:
        result = ai_client.qa_answer(
            question,
            context,
            request_label="manual.qa.answer",
            source_lang=source_lang,
            titles=titles,
        )
        if result and result.get("answer") and _is_valid_answer(result["answer"]) and result["answer"] != "文档中未找到相关信息":
            return {
                "answer": result["answer"],
                "source": result.get("source", ""),
            }
    except Exception:
        pass

    try:
        if source_lang == "en":
            prompt = f"""You are a technical manual assistant. Answer from the excerpts below.

Manual: {title_str}

Excerpts:
{context[:12000]}

Question: {question}

Use the original English sentences and terms from the manual. Keep names, models, numbers, and units unchanged. Write the answer in English.
Format as Markdown lists: heading per topic, numbered steps `1. 2. 3.`, and `- ` bullets for table rows, models, and times. Keep original wording inside each item. Do not collapse the answer into one paragraph.
Answer from this one manual only."""
        else:
            prompt = f"""你是一个技术文档助手。请根据以下说明书内容回答用户问题。
说明书名称：{title_str}

说明书内容片段：
{context[:12000]}

用户问题：{question}

要求：
1. 优先基于提供的文档片段回答
2. 如果片段中有部分相关信息但不够完整，基于已有信息尽量回答，并说明信息可能不完整
3. 只有在片段与问题完全无关时才说明未找到相关信息
4. 用说明书原文作答，紧贴原文句子和用词，不要意译
5. 严格使用文档中的原始术语
6. 保持文档中的产品名、型号、参数、单位等专有信息完全不变
7. 操作步骤必须按顺序用 Markdown 有序列表完整写出每一步；整理成列表时只改格式，不改原文语义
8. 当前页同时出现「根据步骤1-6 / 1-7」和「操作步骤如下」时：前者写入「提示」小节，后者之后的编号才作为有序列表；不要把「根据步骤1-6」写成第1步
9. 只有「根据步骤1-6」而没有当前页操作步骤、且上下文有步骤1-6正文时，再展开这些步骤；找不到前置步骤时，把当前章节已有操作步骤完整列出
10. 页面有插图、孔位图、试剂体积标注时，文字保留孔位和体积
11. 只根据当前这一本说明书作答，不要混入其他型号
12. 中文说明书用中文原文作答，英文说明书用英文原文作答"""
        messages = [{"role": "user", "content": prompt}]
        fallback_answer = ai_client.chat(messages, max_tokens=4096, temperature=0.3, request_label="manual.qa.fallback")
        if _is_valid_answer(fallback_answer):
            return {"answer": fallback_answer.strip(), "source": title_str}
    except Exception:
        pass

    snippet_preview = context[:1500].strip()
    if snippet_preview:
        return {"answer": f"AI 引擎暂时不可用，以下是文档中与您问题相关的原始内容片段，供参考：\n\n{snippet_preview}", "source": title_str}

    return {"answer": "当前已选文档中未检索到相关内容。", "source": ""}





def _session_store():
    return UPLOAD_SESSIONS.setdefault("sessions", {})


def _materialize_official(item: dict, user_key: str) -> dict:
    file_id = cache_file_id(item)
    uploads = UPLOAD_SESSIONS.setdefault(user_key, {})
    cached = uploads.get(file_id)
    if cached and cached.get("pages"):
        return cached
    dest = os.path.join(OFFICIAL_DIR, f"{file_id}.pdf")
    if not os.path.exists(dest):
        files_path = item.get("files") or ""
        download_official_pdf(files_path, dest)
    pages = _extract_pdf_pages(dest)
    if not pages:
        raise HTTPException(status_code=400, detail="说明书解析失败，请更换手册或补充上传")
    title = item.get("title") or file_id
    rec = {
        "file_id": file_id,
        "filename": f"{title}.pdf",
        "title": title,
        "pages": pages,
        "total_pages": len(pages),
        "file_path": dest,
        "file_size": os.path.getsize(dest),
        "official_item": item,
    }
    uploads[file_id] = rec
    return rec


def _docs_from_uploads(user_key: str, file_ids: List[str]) -> List[dict]:
    uploads = UPLOAD_SESSIONS.get(user_key, {})
    selected = []
    for fid in file_ids:
        if fid in uploads:
            selected.append(uploads[fid])
    if not selected:
        raise HTTPException(status_code=400, detail="未找到上传文件，请重新上传")
    return selected


def _resolve_manual_pdf(file_id: str, user_key: str = "") -> Optional[str]:
    if not file_id:
        return None
    if user_key:
        rec = (UPLOAD_SESSIONS.get(user_key) or {}).get(file_id) or {}
        path = rec.get("file_path")
        if path and os.path.exists(path):
            return path
    for folder in (OFFICIAL_DIR, TEMP_DIR):
        candidate = os.path.join(folder, f"{file_id}.pdf")
        if os.path.exists(candidate):
            return candidate
    for key, uploads in UPLOAD_SESSIONS.items():
        if key == "sessions" or not isinstance(uploads, dict):
            continue
        rec = uploads.get(file_id) or {}
        path = rec.get("file_path")
        if path and os.path.exists(path):
            return path
    return None


def _render_page_jpeg(file_path: str, page_num: int, scale: float = 1.6, quality: int = 82) -> Optional[bytes]:
    if not file_path or not os.path.exists(file_path):
        return None
    try:
        page_num = int(page_num)
    except (TypeError, ValueError):
        return None
    doc = None
    try:
        doc = fitz.open(file_path)
        if page_num < 1 or page_num > doc.page_count:
            return None
        page = doc[page_num - 1]
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        return pix.tobytes("jpeg", jpg_quality=quality)
    except Exception:
        return None
    finally:
        if doc is not None:
            doc.close()


def _build_page_images(documents: List[dict], sources: List[dict], limit: int = 2) -> List[dict]:
    docs_by_title = {d.get("title"): d for d in documents}
    docs_by_id = {d.get("file_id"): d for d in documents if d.get("file_id")}
    images = []
    seen = set()
    for item in sources:
        title = item.get("title")
        try:
            page = int(item.get("page") or 0)
        except (TypeError, ValueError):
            continue
        file_id = item.get("file_id")
        rec = docs_by_id.get(file_id) or docs_by_title.get(title) or {}
        path = rec.get("file_path")
        fid = rec.get("file_id") or file_id
        if (not path or not os.path.exists(path)) and fid:
            path = _resolve_manual_pdf(fid)
        if page <= 0 or not path or not os.path.exists(path):
            continue
        key = (fid or title, page)
        if key in seen:
            continue
        raw = _render_page_jpeg(path, page)
        if not raw:
            continue
        seen.add(key)
        images.append({
            "file_id": fid,
            "page": page,
            "title": title,
            "data_url": "data:image/jpeg;base64," + base64.b64encode(raw).decode("ascii"),
        })
        if len(images) >= limit:
            break
    return images


def _answer_one_doc(question: str, documents: List[dict]) -> dict:
    titles = [d.get("title", "") for d in documents]
    file_by_title = {d.get("title", ""): d.get("file_id") for d in documents}
    ranked = _rank_page_chunks(question, documents, limit=10)
    expanded = _expand_ranked_with_neighbors(ranked, documents, question=question)
    context = _build_context(_order_context_sources(expanded), max_chars=14000)
    result = _call_ai_with_citations(question, context, titles)
    is_fallback = result.get("answer") in ("当前已选文档中未检索到相关内容。", "文档中未找到相关信息")
    search_hit = 1 if (ranked and not is_fallback) else 0
    relevance_score = round(ranked[0]["score"], 4) if ranked else 0.0
    return_sources = []
    if not is_fallback and ranked:
        seen = set()
        for s in ranked[:8]:
            key = f"{s['title']}_{s['page_num']}"
            if key in seen:
                continue
            if _competing_chapter_penalty(question, s.get("chunk") or "") < 0:
                continue
            seen.add(key)
            return_sources.append({
                "title": s["title"],
                "page": s["page_num"],
                "content": s.get("chunk", "")[:150],
                "file_id": file_by_title.get(s["title"]),
            })
            if len(return_sources) >= 4:
                break
    source_for_db = [{"title": s["title"], "page": s["page"], "file_id": s.get("file_id")} for s in return_sources]
    return {
        "answer": result["answer"],
        "sources": return_sources,
        "source_for_db": source_for_db,
        "search_hit": search_hit,
        "relevance_score": relevance_score,
        "titles": titles,
    }


def _combine_per_manual_answers(documents: List[dict], results: List[dict]) -> dict:
    parts = []
    sources = []
    source_for_db = []
    for doc, one in zip(documents, results):
        title = doc.get("title") or "说明书"
        answer = ((one or {}).get("answer") or "").strip()
        parts.append(f"## {title}\n\n{answer}" if answer else f"## {title}\n\n该手册中未找到相关内容。")
        sources.extend((one or {}).get("sources") or [])
        source_for_db.extend((one or {}).get("source_for_db") or [])
    return {
        "answer": "\n\n".join(parts),
        "sources": sources[:8],
        "source_for_db": source_for_db[:8],
        "search_hit": 1 if any((r or {}).get("search_hit") for r in results) else 0,
        "relevance_score": max(((r or {}).get("relevance_score") or 0) for r in results) if results else 0.0,
        "titles": [d.get("title", "") for d in documents],
    }


def _answer_from_docs(question: str, documents: List[dict]) -> dict:
    documents = documents or []
    if len(documents) <= 1:
        return _answer_one_doc(question, documents)
    workers = min(4, len(documents))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_answer_one_doc, question, [doc]) for doc in documents]
        results = [fut.result() for fut in futs]
    return _combine_per_manual_answers(documents, results)


@router.post("/query")
async def query_official_manual(
    input_data: QueryInput,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    started = time.perf_counter()
    user_id = _get_user_id_from_token(token, db)
    question = (input_data.question or "").strip()
    product = (input_data.product or "").strip()
    site = normalize_site(input_data.site)
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空")

    user_key = user_id or "anonymous"
    store = _session_store()
    sess = None
    sess_data = {}
    if input_data.session_id:
        sess = db.query(QaSession).filter(
            QaSession.id == input_data.session_id,
            QaSession.user_id == user_id,
        ).first()
        if not sess:
            raise HTTPException(status_code=404, detail="会话不存在")
        sess_data = store.get(str(sess.id), {})

    keywords = extract_search_keywords(question, product)
    keyword = "、".join(keywords) if keywords else extract_search_keyword(question, product)
    candidates = sess_data.get("candidates") or []
    selected_meta = []
    documents = []
    miss_message = ""
    status = "answered"
    ranked = []

    if input_data.file_ids:
        documents = _docs_from_uploads(user_key, input_data.file_ids)
    elif input_data.official_ids:
        raw_candidates = sess_data.get("official_candidates") or sess_data.get("candidates") or []
        picked = pick_from_candidates(raw_candidates, input_data.official_ids)
        if not picked:
            items = search_official_manuals_for_keywords(keywords, limit=10, site=site)
            ranked = filter_manuals_by_keywords(items, keywords)
            ranked = filter_manuals_by_lang(ranked, site)
            ranked = rank_manuals_for_keywords(ranked, question, keywords, lang=site)
            candidates = [public_item(x) for x in ranked]
            picked = pick_from_candidates(ranked, input_data.official_ids)
        if not picked:
            status = "miss"
            miss_message = "未找到指定说明书，请重新选择或改问。"
        else:
            selected_meta = picked
            if _offline_pdf_unavailable(picked, user_key):
                status = "miss"
                miss_message = "离线缓存命中了手册索引，但本地还没有该 PDF。联网后会自动缓存，也可直接上传说明书继续问。"
            else:
                try:
                    documents = [_materialize_official(item, user_key) for item in picked]
                except HTTPException:
                    raise
                except Exception:
                    logger.exception("download/parse official manual failed")
                    status = "miss"
                    miss_message = "已定位手册，但下载或解析失败。可更换手册或补充上传后再问。"
    elif sess_data.get("documents") and (not product or product == sess_data.get("product")) and site == sess_data.get("site", "zh"):
        documents = sess_data.get("documents") or []
        selected_meta = sess_data.get("official_items") or []
        candidates = sess_data.get("candidates") or []
    else:
        try:
            items = search_official_manuals_for_keywords(keywords, limit=10, site=site)
        except OfficialSearchError as exc:
            items = []
            status = "miss"
            miss_message = f"暂时无法打开电子说明书库（{exc.library_url}），请稍后重试。"
        except Exception:
            items = []
        ranked = filter_manuals_by_keywords(items, keywords)
        ranked = filter_manuals_by_lang(ranked, site)
        ranked = rank_manuals_for_keywords(ranked, question, keywords, lang=site)
        candidates = [public_item(x) for x in ranked]
        if needs_user_choice_for_keywords(ranked, keywords):
            status = "choose"
            miss_message = "找到多本相关说明书，请勾选一本或多本后再作答。"
        else:
            picked = select_manuals_for_keywords(ranked, question, keywords)
            if not picked:
                status = "miss"
                if not miss_message:
                    miss_message = f"电子说明书库未找到与「{keyword}」匹配的说明书。可改型号后再试，或补充说明书后继续问。"
            else:
                selected_meta = picked
                if _offline_pdf_unavailable(picked, user_key):
                    status = "miss"
                    miss_message = "离线缓存命中了手册索引，但本地还没有该 PDF。联网后会自动缓存，也可直接上传说明书继续问。"
                else:
                    try:
                        documents = [_materialize_official(item, user_key) for item in picked]
                    except HTTPException:
                        raise
                    except Exception:
                        logger.exception("download/parse official manual failed")
                        status = "miss"
                        miss_message = "已定位手册，但下载或解析失败。可更换手册或补充上传后再问。"

    titles = [d.get("title", "") for d in documents] if documents else [m.get("title", "") for m in selected_meta]
    summary_title = _session_title(question, product)
    if not sess:
        sess = QaSession(user_id=user_id, session_type="manual", title=summary_title)
        db.add(sess)
        db.commit()
        db.refresh(sess)

    selected_public = [public_item(x) if "title" in x else x for x in selected_meta]
    payload = {
        "session_id": sess.id,
        "status": status,
        "keyword": keyword,
        "selected": selected_public,
        "candidates": candidates[:8],
        "titles": titles,
        "answer": "",
        "sources": [],
        "message": miss_message,
        "site": site,
    }

    if status == "choose":
        payload["status"] = "choose"
        payload["answer"] = miss_message or "找到多本相关说明书，请勾选一本或多本后再作答。"
        _save_qa_history(
            db=db, session_type="manual", question=question,
            answer_data={"answer": payload["answer"], "sources": []},
            user_id=user_id, session_id=sess.id,
            sources=[], search_hit=0, relevance_score=0.0,
            duration_ms=_elapsed_ms(started),
        )
        store[str(sess.id)] = {
            "session_id": sess.id,
            "title": sess.title,
            "titles": titles,
            "documents": documents,
            "candidates": candidates[:8],
            "official_candidates": ranked or sess_data.get("official_candidates") or selected_meta,
            "official_items": selected_meta,
            "keyword": keyword,
            "product": product,
            "site": site,
        }
        return payload

    if status == "miss" or not documents:
        payload["status"] = "miss"
        payload["answer"] = miss_message or "电子说明书库未找到匹配的说明书。"
        _save_qa_history(
            db=db, session_type="manual", question=question,
            answer_data={"answer": payload["answer"], "sources": []},
            user_id=user_id, session_id=sess.id,
            sources=[], search_hit=0, relevance_score=0.0,
            duration_ms=_elapsed_ms(started),
        )
        store[str(sess.id)] = {
            "session_id": sess.id,
            "title": sess.title,
            "titles": titles,
            "documents": documents,
            "candidates": candidates[:8],
            "official_candidates": ranked or sess_data.get("official_candidates") or selected_meta,
            "official_items": selected_meta,
            "keyword": keyword,
            "product": product,
            "site": site,
        }
        return payload

    result = _answer_from_docs(question, documents)
    payload["answer"] = result["answer"]
    payload["sources"] = result["sources"]
    payload["titles"] = result["titles"]
    if not result["titles"]:
        payload["message"] = ""
    elif len(result["titles"]) == 1:
        payload["message"] = f"本次依据《{result['titles'][0]}》作答"
    else:
        joined = "、".join(f"《{t}》" for t in result["titles"])
        payload["message"] = f"本次依据 {joined} 作答，便于横向对照"

    _save_qa_history(
        db=db, session_type="manual", question=question,
        answer_data={"answer": result["answer"], "sources": result["source_for_db"]},
        user_id=user_id, session_id=sess.id,
        sources=result["source_for_db"],
        search_hit=result["search_hit"],
        relevance_score=result["relevance_score"],
        duration_ms=_elapsed_ms(started),
    )

    store[str(sess.id)] = {
        "session_id": sess.id,
        "title": sess.title,
        "titles": result["titles"],
        "documents": documents,
        "candidates": candidates[:8],
        "official_candidates": ranked or sess_data.get("official_candidates") or selected_meta,
        "official_items": selected_meta,
        "keyword": keyword,
        "product": product,
        "total_pages": sum(d.get("total_pages", 0) for d in documents),
        "site": site,
    }
    return payload


@router.post("/upload")
async def upload_manuals(
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    user_id = _get_user_id_from_token(token, db)
    uploaded = []

    for file in files:
        if not file.filename:
            continue

        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in (".pdf",):
            uploaded.append({"filename": file.filename, "status": "error", "error": "仅支持 PDF 文件"})
            continue

        file_id = uuid.uuid4().hex[:12]
        save_path = os.path.join(TEMP_DIR, f"{file_id}{ext}")

        try:
            with open(save_path, "wb") as f:
                content = await file.read()
                f.write(content)
        except Exception:
            uploaded.append({"filename": file.filename, "status": "error", "error": "文件保存失败"})
            continue

        pages = _extract_pdf_pages(save_path)
        if not pages:
            os.remove(save_path)
            uploaded.append({"filename": file.filename, "status": "error", "error": "PDF 解析失败"})
            continue

        title = os.path.splitext(file.filename)[0]
        key = user_id or "anonymous"
        if key not in UPLOAD_SESSIONS:
            UPLOAD_SESSIONS[key] = {}
        UPLOAD_SESSIONS[key][file_id] = {
            "file_id": file_id,
            "filename": file.filename,
            "title": title,
            "pages": pages,
            "total_pages": len(pages),
            "file_path": save_path,
            "file_size": len(content),
        }

        uploaded.append({
            "file_id": file_id,
            "filename": file.filename,
            "title": title,
            "total_pages": len(pages),
            "status": "ok",
        })

    return {"uploaded": uploaded, "total": len(uploaded)}


@router.get("/uploads")
async def list_uploads(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    user_id = _get_user_id_from_token(token, db)
    key = user_id or "anonymous"
    files = UPLOAD_SESSIONS.get(key, {})
    return [{
        "file_id": v["file_id"],
        "filename": v["filename"],
        "title": v["title"],
        "total_pages": v["total_pages"],
        "file_size": v.get("file_size", 0),
    } for v in files.values()]


@router.delete("/uploads/{file_id}")
async def delete_upload(file_id: str, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    user_id = _get_user_id_from_token(token, db)
    key = user_id or "anonymous"
    files = UPLOAD_SESSIONS.get(key, {})
    if file_id not in files:
        raise HTTPException(status_code=404, detail="文件不存在")
    file_path = files[file_id].get("file_path")
    if file_path and os.path.exists(file_path):
        os.remove(file_path)
    del files[file_id]
    return {"message": "已删除"}


@router.post("/start")
async def start_session(
    input_data: StartSessionInput,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    user_id = _get_user_id_from_token(token, db)
    key = user_id or "anonymous"
    uploads = UPLOAD_SESSIONS.get(key, {})

    if not input_data.file_ids:
        raise HTTPException(status_code=400, detail="请至少选择一个文件")

    selected = []
    for fid in input_data.file_ids:
        if fid in uploads:
            selected.append(uploads[fid])

    if not selected:
        raise HTTPException(status_code=400, detail="未找到选中的文件，请重新上传")

    titles = [s["title"] for s in selected]
    summary_title = "、".join(titles[:2])
    if len(titles) > 2:
        summary_title += f" 等{len(titles)}份说明书"

    total_chars = sum(len("\n".join(p["text"] for p in s.get("pages", []))) for s in selected)

    sess = QaSession(user_id=user_id, session_type="manual", title=summary_title[:80])
    db.add(sess)
    db.commit()
    db.refresh(sess)

    session_data = {
        "session_id": sess.id,
        "title": summary_title,
        "titles": titles,
        "documents": [{
            "title": s["title"],
            "pages": s["pages"],
            "file_path": s["file_path"],
        } for s in selected],
        "total_pages": sum(s["total_pages"] for s in selected),
        "total_chars": total_chars,
    }

    sess_key = str(sess.id)
    if "sessions" not in UPLOAD_SESSIONS:
        UPLOAD_SESSIONS["sessions"] = {}
    UPLOAD_SESSIONS["sessions"][sess_key] = session_data

    return {
        "session_id": sess.id,
        "title": summary_title,
        "titles": titles,
        "total_pages": session_data["total_pages"],
        "total_chars": total_chars,
        "message": f"已加载 {len(titles)} 份说明书，共 {session_data['total_pages']} 页、{total_chars} 字符，可以开始提问。",
    }


@router.post("/ask")
async def ask_manual(
    input_data: AskInput,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    started = time.perf_counter()
    user_id = _get_user_id_from_token(token, db)
    question = (input_data.question or "").strip()

    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空")

    sess = db.query(QaSession).filter(
        QaSession.id == input_data.session_id,
        QaSession.user_id == user_id,
    ).first()
    if not sess:
        raise HTTPException(status_code=404, detail="会话不存在")

    sess_data = UPLOAD_SESSIONS.get("sessions", {}).get(str(sess.id))
    if not sess_data:
        raise HTTPException(status_code=400, detail="会话数据已过期，请重新开始")

    documents = sess_data.get("documents", [])
    titles = sess_data.get("titles", [])

    ranked = _rank_page_chunks(question, documents, limit=10)
    context = _build_context(ranked, max_chars=10000)
    result = _call_ai_with_citations(question, context, titles)

    is_fallback = (result.get("answer") == "当前已选文档中未检索到相关内容。"
                   or result.get("answer") == "文档中未找到相关信息")
    search_hit = 1 if (ranked and not is_fallback) else 0
    relevance_score = round(ranked[0]["score"], 4) if ranked else 0.0

    return_sources = []
    if not is_fallback and ranked:
        seen = set()
        for s in ranked[:4]:
            key = f"{s['title']}_{s['page_num']}"
            if key not in seen:
                seen.add(key)
                return_sources.append(
                    {"title": s["title"], "page": s["page_num"], "content": s.get("chunk", "")[:150]}
                )

    source_for_db = []
    seen_db = set()
    for s in ranked[:4]:
        key = f"{s['title']}_{s['page_num']}"
        if key not in seen_db:
            seen_db.add(key)
            source_for_db.append({"title": s["title"], "page": s["page_num"]})

    answer_data = {
        "answer": result["answer"],
        "sources": [{"title": s["title"], "page": s["page"]} for s in return_sources] if not is_fallback else [],
    }

    _save_qa_history(
        db=db, session_type="manual", question=question,
        answer_data=answer_data, user_id=user_id, session_id=sess.id,
        sources=source_for_db, search_hit=search_hit, relevance_score=relevance_score,
        duration_ms=_elapsed_ms(started),
    )

    return {
        "session_id": sess.id,
        "answer": result["answer"],
        "sources": return_sources,
    }


@router.get("/preview/{file_id}")
async def preview_file(
    file_id: str,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    user_id = _get_user_id_from_token(token, db)
    key = user_id or "anonymous"
    file_data = (UPLOAD_SESSIONS.get(key) or {}).get(file_id) or {}
    file_path = _resolve_manual_pdf(file_id, key)
    if not file_path:
        raise HTTPException(status_code=404, detail="文件不存在")
    filename = file_data.get("filename") or os.path.basename(file_path)
    return FileResponse(file_path, media_type="application/pdf", filename=filename)


@router.get("/page-image/{file_id}/{page}")
async def page_image(
    file_id: str,
    page: int,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    user_id = _get_user_id_from_token(token, db)
    file_path = _resolve_manual_pdf(file_id, user_id or "anonymous")
    if not file_path:
        raise HTTPException(status_code=404, detail="文件不存在")
    data = _render_page_jpeg(file_path, page)
    if not data:
        raise HTTPException(status_code=404, detail="页码无效")
    return Response(content=data, media_type="image/jpeg")


@router.get("/download/{file_id}")
async def download_file(
    file_id: str,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    user_id = _get_user_id_from_token(token, db)
    key = user_id or "anonymous"
    uploads = UPLOAD_SESSIONS.get(key, {})

    file_data = uploads.get(file_id)
    if not file_data:
        raise HTTPException(status_code=404, detail="文件不存在")

    file_path = file_data.get("file_path")
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="文件已过期")

    return FileResponse(
        file_path, media_type="application/pdf",
        filename=file_data.get("filename", "manual.pdf"),
        headers={"Content-Disposition": f"attachment; filename=\"{file_data.get('filename', 'manual.pdf')}\""}
    )


@router.get("/sessions")
async def get_sessions(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    user_id = _get_user_id_from_token(token, db)
    sessions = db.query(QaSession).filter(
        QaSession.user_id == user_id,
        QaSession.session_type == "manual",
    ).order_by(QaSession.updated_at.desc()).all()

    return [{
        "id": s.id,
        "title": s.title,
        "session_type": s.session_type,
        "created_at": _to_beijing_iso(s.created_at),
        "updated_at": _to_beijing_iso(s.updated_at),
    } for s in sessions]


@router.get("/sessions/{session_id}")
async def get_session_detail(
    session_id: int,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    user_id = _get_user_id_from_token(token, db)
    sess = db.query(QaSession).filter(
        QaSession.id == session_id,
        QaSession.user_id == user_id,
    ).first()
    if not sess:
        raise HTTPException(status_code=404, detail="会话不存在")

    messages = db.query(QaMessage).filter(
        QaMessage.session_id == session_id,
    ).order_by(QaMessage.created_at.asc()).all()

    sess_data = UPLOAD_SESSIONS.get("sessions", {}).get(str(session_id), {})

    return {
        "session": {
            "id": sess.id,
            "title": sess.title,
            "created_at": _to_beijing_iso(sess.created_at),
            "updated_at": _to_beijing_iso(sess.updated_at),
            "titles": sess_data.get("titles", []),
            "total_pages": sess_data.get("total_pages", 0),
            "candidates": sess_data.get("candidates", []),
        },
        "messages": [{
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "sources": json.loads(m.sources) if m.sources else [],
            "created_at": _to_beijing_iso(m.created_at),
        } for m in messages],
    }


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: int,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    user_id = _get_user_id_from_token(token, db)
    sess = db.query(QaSession).filter(
        QaSession.id == session_id,
        QaSession.user_id == user_id,
    ).first()
    if not sess:
        raise HTTPException(status_code=404, detail="会话不存在")

    db.query(QaMessage).filter(QaMessage.session_id == session_id).delete()
    db.delete(sess)
    db.commit()

    sess_data = UPLOAD_SESSIONS.get("sessions", {}).pop(str(session_id), None)
    if sess_data:
        for doc in sess_data.get("documents", []):
            fp = doc.get("file_path")
            if fp and os.path.exists(fp):
                try:
                    os.remove(fp)
                except Exception:
                    pass

    return {"message": "会话已删除"}
