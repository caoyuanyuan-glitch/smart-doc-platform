from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from sqlalchemy.orm import Session
import os
from app.database import get_db
from app.crud.document import create_document, get_document, get_documents, delete_document
from app.schemas.document import Document, DocumentListItem
from app.utils.document_parser import parse_file, get_file_type

router = APIRouter()

UPLOAD_DIR = "./static/uploads"

@router.post("/upload/")
async def upload_file(file: UploadFile = File(...), db: Session = Depends(get_db)):
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
            user_id=1
        )
        from app.crud.document import update_document_status
        update_document_status(db, document.id, "ready")
        from app.crud.document import update_document_file_size
        update_document_file_size(db, document.id, file_size)
        return {"message": "File uploaded successfully", "document_id": document.id}
    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/", response_model=list[DocumentListItem])
async def read_documents(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    documents = get_documents(db, skip=skip, limit=limit)
    return documents

@router.get("/{document_id}", response_model=Document)
async def read_document(document_id: int, db: Session = Depends(get_db)):
    document = get_document(db, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return document

@router.delete("/{document_id}")
async def delete_document_endpoint(document_id: int, db: Session = Depends(get_db)):
    document = get_document(db, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    delete_document(db, document_id)
    return {"message": "Document deleted successfully"}
