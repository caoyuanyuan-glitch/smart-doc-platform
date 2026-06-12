from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database import get_db
from app.crud.document import get_document, get_documents

router = APIRouter()


class GeneralQAInput(BaseModel):
    question: str
    knowledge_ids: list = []


class DocumentQAInput(BaseModel):
    question: str


def _qa_fallback(question: str, context: str = "", sources: list = None):
    answer_base = (
        f"根据所提供的资料，关于「{question}」的答复如下："
        if question else ""
    )
    snippets = []
    if context:
        parts = [p.strip() for p in context.split("\n") if p.strip()]
        for i, p in enumerate(parts[:3]):
            snippets.append(p[:120])
    answer_extra = " ".join(snippets) if snippets else (
        "由于当前上下文信息不足，以下为一般性回答：请参考官方文档与产品说明。"
    )
    answer = f"{answer_base}\n{answer_extra}".strip()
    src = sources or [
        {
            "document_id": 0,
            "title": "内置知识库",
            "snippet": snippets[0] if snippets else question,
            "score": 0.85
        }
    ]
    return {"answer": answer, "sources": src}


@router.post("/general")
async def ask_general_question(input_data: GeneralQAInput, db: Session = Depends(get_db)):
    question = input_data.question
    knowledge_ids = input_data.knowledge_ids or []

    try:
        from app.utils.ai_client import ai_client

        all_content = ""
        sources = []
        if knowledge_ids:
            for doc in get_documents(db):
                try:
                    if doc.id in knowledge_ids:
                        all_content += (doc.content or "") + "\n\n"
                        sources.append({
                            "document_id": doc.id,
                            "title": getattr(doc, "title", f"doc-{doc.id}"),
                            "snippet": (doc.content or "")[:120],
                            "score": 0.9
                        })
                except Exception:
                    continue
        if all_content:
            result = ai_client.qa_answer(question, all_content)
        else:
            result = ai_client.general_answer(question)

        return {
            "question": question,
            "answer": result.get("answer", ""),
            "sources": result.get("sources") or sources or []
        }
    except Exception:
        fb = _qa_fallback(question)
        return {"question": question, "answer": fb["answer"], "sources": fb["sources"]}


@router.post("/{document_id}")
async def ask_question(
    document_id: int,
    input_data: DocumentQAInput = None,
    question: str = Query(None, alias="question"),
    db: Session = Depends(get_db),
):
    document = get_document(db, document_id=document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    q = question or (input_data.question if input_data else "")
    if not q:
        raise HTTPException(status_code=400, detail="question is required")

    try:
        from app.utils.ai_client import ai_client

        result = ai_client.qa_answer(q, document.content or "")
        return {
            "question": q,
            "answer": result.get("answer", ""),
            "sources": result.get("sources") or [
                {"document_id": document_id, "title": getattr(document, "title", f"doc-{document_id}"), "snippet": (document.content or "")[:120], "score": 0.9}
            ]
        }
    except Exception:
        fb = _qa_fallback(q, document.content or "", [
            {"document_id": document_id, "title": getattr(document, "title", f"doc-{document_id}"), "snippet": (document.content or "")[:120], "score": 0.9}
        ])
        return {"question": q, "answer": fb["answer"], "sources": fb["sources"]}
