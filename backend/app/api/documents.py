from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from sqlalchemy.orm import Session
import os
from app.database import get_db
from app.crud.document import create_document, get_document, get_documents, delete_document
from app.crud.review import delete_reviews_by_document
from app.schemas.document import Document, DocumentListItem
from app.schemas.user import UserOut
from app.api.auth import get_current_active_user
from app.utils.document_parser import parse_file, get_file_type

router = APIRouter()

UPLOAD_DIR = "./static/uploads"


def _ensure_document_access(document, current_user: UserOut):
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    if current_user.role == "admin":
        return document
    if document.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问该文档")
    return document

@router.post("/upload/", response_model=DocumentListItem)
async def upload_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: UserOut = Depends(get_current_active_user),
):
    if not os.path.exists(UPLOAD_DIR):
        os.makedirs(UPLOAD_DIR, exist_ok=True)
    
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    file_size = 0
    try:
        with open(file_path, "wb") as buffer:
            while chunk := await file.read(1024 * 1024):
                buffer.write(chunk)
                file_size += len(chunk)
    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=500, detail=f"文件保存失败: {str(e)}")
    
    try:
        content = parse_file(file_path)
        file_type = get_file_type(file.filename)
        preview = content[:500] + "..." if len(content) > 500 else content
        
        from app.schemas.document import DocumentCreate
        document = create_document(
            db=db,
            document=DocumentCreate(filename=file.filename, file_type=file_type, content=content, preview=preview),
            user_id=current_user.id,
        )
        from app.crud.document import update_document_status
        document = update_document_status(db, document.id, "ready")
        from app.crud.document import update_document_file_size
        document = update_document_file_size(db, document.id, file_size)
        return document
    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/", response_model=list[DocumentListItem])
async def read_documents(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: UserOut = Depends(get_current_active_user),
):
    owner_id = None if current_user.role == "admin" else current_user.id
    documents = get_documents(db, user_id=owner_id, skip=skip, limit=limit)
    return documents

@router.get("/{document_id}", response_model=Document)
async def read_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: UserOut = Depends(get_current_active_user),
):
    document = _ensure_document_access(get_document(db, document_id), current_user)
    return document

@router.delete("/{document_id}")
async def delete_document_endpoint(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: UserOut = Depends(get_current_active_user),
):
    document = _ensure_document_access(get_document(db, document_id), current_user)
    filename = str(getattr(document, "filename", "") or "")
    if filename.startswith("文本片段_"):
        delete_reviews_by_document(db, document_id)
    delete_document(db, document_id)
    return {"message": "Document deleted successfully"}
