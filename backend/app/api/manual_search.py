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
from app.database import get_db
from app.models.qa_history import QaSession, QaMessage
from app.api.auth import oauth2_scheme
from app.api.qa import (
    _tokenize, _char_ngrams, _normalize_text,
    _split_content_to_chunks, _score_chunk,
    _get_user_id_from_token, _save_qa_history, _to_beijing_iso,
)
from app.utils.ai_client import ai_client

router = APIRouter()

BEIJING_TZ = timezone(timedelta(hours=8))
TEMP_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "manual_uploads")
os.makedirs(TEMP_DIR, exist_ok=True)

UPLOAD_SESSIONS = {}


class StartSessionInput(BaseModel):
    file_ids: List[str]


class AskInput(BaseModel):
    session_id: int
    question: str


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


def _split_pages_to_chunks(pages: List[dict], chunk_size: int = 400, overlap: int = 80) -> List[dict]:
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


def _rank_page_chunks(question: str, documents: List[dict], limit: int = 6) -> List[dict]:
    all_chunks = []
    for doc in documents:
        chunks = _split_pages_to_chunks(doc.get("pages", []))
        for ch in chunks:
            score = _score_chunk(question, ch["text"], doc.get("title", ""))
            if score > 0:
                all_chunks.append({
                    "title": doc.get("title", "未知"),
                    "chunk": ch["text"],
                    "page_num": ch["page_num"],
                    "score": score,
                })
    all_chunks.sort(key=lambda x: x["score"], reverse=True)
    return all_chunks[:limit]


def _build_context(sources: List[dict], max_chars: int = 6000) -> str:
    parts = []
    total = 0
    for i, s in enumerate(sources):
        block = f"【来源 {i+1}】文档「{s['title']}」第 {s['page_num']} 页\n{s['chunk']}"
        if total + len(block) > max_chars:
            break
        parts.append(block)
        total += len(block)
    return "\n\n---\n\n".join(parts)


def _call_ai_with_citations(question: str, context: str, titles: List[str]) -> dict:
    fallback = "当前已选文档中未检索到相关内容。"

    try:
        result = ai_client.qa_answer(question, context)
        if result and result.get("answer") and result.get("answer") != "文档中未找到相关信息":
            return {
                "answer": result["answer"],
                "source": result.get("source", ""),
            }
    except Exception:
        pass

    return {"answer": fallback, "source": ""}





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

    ranked = _rank_page_chunks(question, documents, limit=6)
    context = _build_context(ranked, max_chars=6000)
    result = _call_ai_with_citations(question, context, titles)

    is_fallback = (result.get("answer") == "当前已选文档中未检索到相关内容。"
                   or result.get("answer") == "文档中未找到相关信息")

    return_sources = []
    if not is_fallback and ranked:
        return_sources = [
            {"title": s["title"], "page": s["page_num"], "content": s.get("chunk", "")[:150]}
            for s in ranked[:4]
        ]

    source_for_db = [{"title": s["title"], "page": s["page_num"]} for s in ranked[:4]]

    answer_data = {
        "answer": result["answer"],
        "sources": [{"title": s["title"], "page": s["page_num"]} for s in ranked[:4]] if not is_fallback else [],
    }

    _save_qa_history(
        db=db, session_type="manual", question=question,
        answer_data=answer_data, user_id=user_id, session_id=sess.id,
        sources=source_for_db,
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
