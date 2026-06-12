from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database import get_db
from app.crud.document import get_document

router = APIRouter()


class TextPolishInput(BaseModel):
    text: str


def _polish_fallback(text: str):
    import re

    polished_lines = []
    changes = []
    lines = text.split("\n")
    for idx, line in enumerate(lines):
        new_line = line.strip()
        new_line = re.sub(r"\s+", " ", new_line)
        new_line = new_line.replace("  ", " ")
        if new_line and not new_line.endswith((".", "。", "!", "！", "?", "？")):
            if re.search(r"[\u4e00-\u9fff]", new_line):
                new_line = new_line + "。"
            else:
                new_line = new_line + "."
        if new_line != line:
            changes.append({
                "line": idx + 1,
                "original": line,
                "polished": new_line,
                "type": "format" if new_line.strip() != line.strip() else "punctuation"
            })
        polished_lines.append(new_line)

    polished = "\n".join(polished_lines)
    if not changes:
        changes.append({
            "line": 1,
            "original": text[:80],
            "polished": polished[:80],
            "type": "review"
        })
    return {
        "original": text,
        "polished": polished,
        "changes": changes
    }


@router.post("/text")
async def polish_text_endpoint(input_data: TextPolishInput):
    try:
        from app.utils.ai_client import ai_client
        result = ai_client.polish_text(input_data.text)
        changes = result.get("changes") or []
        if not changes:
            for key in ("original", "polished"):
                if result.get(key) and result.get("polished") != result.get("original"):
                    changes.append({
                        "line": 1,
                        "original": result.get("original", "")[:200],
                        "polished": result.get("polished", "")[:200],
                        "type": "ai"
                    })
                    break
        return {
            "original": result.get("original", input_data.text),
            "polished": result.get("polished", input_data.text),
            "changes": changes
        }
    except Exception:
        return _polish_fallback(input_data.text)


@router.post("/{document_id}")
async def polish_document(document_id: int, db: Session = Depends(get_db)):
    document = get_document(db, document_id=document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        from app.utils.ai_client import ai_client
        result = ai_client.polish_text(document.content or "")
        changes = result.get("changes") or []
        return {
            "document_id": document_id,
            "original": result.get("original", document.content or ""),
            "polished": result.get("polished", document.content or ""),
            "changes": changes
        }
    except Exception:
        fb = _polish_fallback(document.content or "")
        fb["document_id"] = document_id
        return fb
