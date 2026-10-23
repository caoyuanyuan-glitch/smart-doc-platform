import os
import re
import json
import uuid
import shutil
import fitz
from typing import Optional, List
from datetime import timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse, FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.api.auth import get_current_active_user
from app.database import get_db
from app.models.qa_history import QaSession, QaMessage
from app.api.auth import oauth2_scheme
from app.api.qa import (
    _tokenize, _char_ngrams, _normalize_text,
    _split_content_to_chunks, _score_chunk,
    _get_user_id_from_token, _save_qa_history, _to_beijing_iso,
)
from app.utils.ai_client import ai_client
from app.utils.official_manual import (
    cache_file_id,
    download_official_pdf,
    extract_search_keyword,
    filter_manuals_by_keyword,
    needs_user_choice,
    pick_from_candidates,
    public_item,
    rank_manuals,
    search_official_manuals,
    select_manuals,
)

router = APIRouter(dependencies=[Depends(get_current_active_user)])

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


def _rank_page_chunks(question: str, documents: List[dict], limit: int = 10) -> List[dict]:
    all_chunks = []
    for doc in documents:
        chunks = _split_pages_to_chunks(doc.get("pages", []))
        for ch in chunks:
            score = _score_chunk(question, ch["text"], doc.get("title", ""))
            all_chunks.append({
                "title": doc.get("title", "未知"),
                "chunk": ch["text"],
                "page_num": ch["page_num"],
                "score": score,
            })
    all_chunks.sort(key=lambda x: x["score"], reverse=True)
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

    try:
        result = ai_client.qa_answer(question, context, request_label="manual.qa.answer")
        if result and result.get("answer") and _is_valid_answer(result["answer"]) and result["answer"] != "文档中未找到相关信息":
            return {
                "answer": result["answer"],
                "source": result.get("source", ""),
            }
    except Exception:
        pass

    try:
        prompt = f"""你是一个技术文档助手。请根据以下说明书内容回答用户问题。

说明书名称：{title_str}

说明书内容片段：
{context[:6000]}

用户问题：{question}

要求：
1. 优先基于提供的文档片段回答
2. 如果片段中有部分相关信息但不够完整，基于已有信息尽量回答，并说明信息可能不完整
3. 只有在片段与问题完全无关时才说明未找到相关信息
4. 使用专业、准确的语言回答
5. 严格使用文档中的原始术语，不得改写替换（如文档写"主机"则必须用"主机"，不能写成"主持人"、"电脑"等）
6. 保持文档中的产品名、型号、参数、单位等专有信息完全不变"""
        messages = [{"role": "user", "content": prompt}]
        fallback_answer = ai_client.chat(messages, max_tokens=2048, temperature=0.3, request_label="manual.qa.fallback")
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


def _answer_from_docs(question: str, documents: List[dict]) -> dict:
    titles = [d.get("title", "") for d in documents]
    file_by_title = {d.get("title", ""): d.get("file_id") for d in documents}
    ranked = _rank_page_chunks(question, documents, limit=10)
    context = _build_context(ranked, max_chars=10000)
    result = _call_ai_with_citations(question, context, titles)
    is_fallback = result.get("answer") in ("当前已选文档中未检索到相关内容。", "文档中未找到相关信息")
    search_hit = 1 if (ranked and not is_fallback) else 0
    relevance_score = round(ranked[0]["score"], 4) if ranked else 0.0
    return_sources = []
    if not is_fallback and ranked:
        seen = set()
        for s in ranked[:4]:
            key = f"{s['title']}_{s['page_num']}"
            if key in seen:
                continue
            seen.add(key)
            return_sources.append({
                "title": s["title"],
                "page": s["page_num"],
                "content": s.get("chunk", "")[:150],
                "file_id": file_by_title.get(s["title"]),
            })
    source_for_db = [{"title": s["title"], "page": s["page"], "file_id": s.get("file_id")} for s in return_sources]
    return {
        "answer": result["answer"],
        "sources": return_sources,
        "source_for_db": source_for_db,
        "search_hit": search_hit,
        "relevance_score": relevance_score,
        "titles": titles,
    }


@router.post("/query")
async def query_official_manual(
    input_data: QueryInput,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    user_id = _get_user_id_from_token(token, db)
    question = (input_data.question or "").strip()
    product = (input_data.product or "").strip()
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

    keyword = extract_search_keyword(question, product)
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
            items = search_official_manuals(keyword, limit=10)
            ranked = rank_manuals(items, question, keyword)
            ranked = filter_manuals_by_keyword(ranked, keyword)
            candidates = [public_item(x) for x in ranked]
            picked = pick_from_candidates(ranked, input_data.official_ids)
        if not picked:
            status = "miss"
            miss_message = "未找到指定说明书，请重新选择或改问。"
        else:
            selected_meta = picked
            try:
                documents = [_materialize_official(item, user_key) for item in picked]
            except HTTPException:
                raise
            except Exception:
                status = "miss"
                miss_message = "已定位手册，但下载或解析失败。可更换手册或补充上传后再问。"
    elif sess_data.get("documents") and (not product or product == sess_data.get("product")):
        documents = sess_data.get("documents") or []
        selected_meta = sess_data.get("official_items") or []
        candidates = sess_data.get("candidates") or []
    else:
        try:
            items = search_official_manuals(keyword, limit=10)
        except Exception:
            items = []
        ranked = rank_manuals(items, question, keyword)
        ranked = filter_manuals_by_keyword(ranked, keyword)
        candidates = [public_item(x) for x in ranked]
        if needs_user_choice(ranked, keyword):
            status = "choose"
            miss_message = "找到多本相关说明书，请选择一本后再作答。"
        else:
            picked = select_manuals(ranked, question, max_count=1)
            if not picked:
                status = "miss"
                miss_message = f"官网未找到与「{keyword}」匹配的说明书。可改型号后再试，或补充说明书后继续问。"
            else:
                selected_meta = picked
                try:
                    documents = [_materialize_official(item, user_key) for item in picked]
                except HTTPException:
                    raise
                except Exception:
                    status = "miss"
                    miss_message = "已定位手册，但下载或解析失败。可更换手册或补充上传后再问。"

    titles = [d.get("title", "") for d in documents] if documents else [m.get("title", "") for m in selected_meta]
    summary_title = (titles[0] if titles else keyword)[:80]
    if not sess:
        sess = QaSession(user_id=user_id, session_type="manual", title=summary_title)
        db.add(sess)
        db.commit()
        db.refresh(sess)
    elif titles:
        sess.title = summary_title
        db.commit()

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
    }

    if status == "choose":
        payload["status"] = "choose"
        payload["answer"] = miss_message or "找到多本相关说明书，请选择一本后再作答。"
        _save_qa_history(
            db=db, session_type="manual", question=question,
            answer_data={"answer": payload["answer"], "sources": []},
            user_id=user_id, session_id=sess.id,
            sources=[], search_hit=0, relevance_score=0.0,
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
        }
        return payload

    if status == "miss" or not documents:
        payload["status"] = "miss"
        payload["answer"] = miss_message or "官网未找到匹配的说明书。"
        _save_qa_history(
            db=db, session_type="manual", question=question,
            answer_data={"answer": payload["answer"], "sources": []},
            user_id=user_id, session_id=sess.id,
            sources=[], search_hit=0, relevance_score=0.0,
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
        }
        return payload

    result = _answer_from_docs(question, documents)
    payload["answer"] = result["answer"]
    payload["sources"] = result["sources"]
    payload["titles"] = result["titles"]
    payload["message"] = f"本次依据《{result['titles'][0]}》作答" if result["titles"] else ""

    _save_qa_history(
        db=db, session_type="manual", question=question,
        answer_data={"answer": result["answer"], "sources": result["source_for_db"]},
        user_id=user_id, session_id=sess.id,
        sources=result["source_for_db"],
        search_hit=result["search_hit"],
        relevance_score=result["relevance_score"],
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
    uploads = UPLOAD_SESSIONS.get(key, {})

    file_data = uploads.get(file_id)
    if not file_data:
        raise HTTPException(status_code=404, detail="文件不存在")

    file_path = file_data.get("file_path")
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="文件已过期")

    return FileResponse(file_path, media_type="application/pdf", filename=file_data.get("filename", "manual.pdf"))


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
