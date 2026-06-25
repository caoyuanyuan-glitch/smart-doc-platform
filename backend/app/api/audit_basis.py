from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from sqlalchemy.orm import Session
import os
from app.database import get_db
from app.crud.audit_basis import create_audit_basis, get_audit_basis, get_audit_bases, delete_audit_basis
from app.schemas.audit_basis import AuditBasis, AuditBasisCreate
from app.utils.document_parser import parse_file, get_file_type

router = APIRouter()

UPLOAD_DIR = "./static/uploads"

@router.post("/upload/")
async def upload_basis(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not os.path.exists(UPLOAD_DIR):
        os.makedirs(UPLOAD_DIR)
    
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())
    
    try:
        content = parse_file(file_path)
        file_type = get_file_type(file.filename)
        
        audit_basis = create_audit_basis(
            db=db,
            audit_basis={"name": file.filename, "content": content, "file_type": file_type}
        )
        
        os.remove(file_path)
        return {"message": "Basis uploaded successfully", "basis_id": audit_basis.id}
    except Exception as e:
        os.remove(file_path)
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/", response_model=list[AuditBasis])
async def read_bases(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    bases = get_audit_bases(db, skip=skip, limit=limit)
    return bases

@router.get("/{basis_id}", response_model=AuditBasis)
async def read_basis(basis_id: int, db: Session = Depends(get_db)):
    basis = get_audit_basis(db, basis_id=basis_id)
    if not basis:
        raise HTTPException(status_code=404, detail="Basis not found")
    return basis

@router.delete("/{basis_id}")
async def delete_basis(basis_id: int, db: Session = Depends(get_db)):
    basis = delete_audit_basis(db, basis_id=basis_id)
    if not basis:
        raise HTTPException(status_code=404, detail="Basis not found")
    return {"message": "Basis deleted successfully"}
