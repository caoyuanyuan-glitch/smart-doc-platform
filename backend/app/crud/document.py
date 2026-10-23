from sqlalchemy.orm import Session
from app.models.document import Document
from app.schemas.document import DocumentCreate
from datetime import datetime

def create_document(db: Session, document: DocumentCreate, user_id: int):
    db_document = Document(
        filename=document.filename,
        file_type=document.file_type,
        content=document.content,
        preview=document.preview,
        user_id=user_id
    )
    db.add(db_document)
    db.commit()
    db.refresh(db_document)
    return db_document

def get_document(db: Session, document_id: int):
    return db.query(Document).filter(Document.id == document_id).first()


def get_documents_by_ids(db: Session, document_ids: list[int]):
    ids = [doc_id for doc_id in document_ids if doc_id is not None]
    if not ids:
        return []
    return db.query(Document).filter(Document.id.in_(ids)).all()

def get_documents(db: Session, user_id: int = None, skip: int = 0, limit: int = 100):
    query = db.query(Document)
    if hasattr(Document, "deleted_at"):
        query = query.filter(Document.deleted_at.is_(None))
    if user_id is not None:
        query = query.filter(Document.user_id == user_id)
    return query.order_by(Document.id.desc()).offset(skip).limit(limit).all()

def delete_document(db: Session, document_id: int):
    document = db.query(Document).filter(Document.id == document_id).first()
    if document:
        from app.models.review import Review
        has_reviews = db.query(Review.id).filter(Review.document_id == document_id).first()
        if has_reviews:
            document.deleted_at = datetime.utcnow()
            document.status = "deleted"
            db.commit()
            db.refresh(document)
        else:
            db.delete(document)
            db.commit()
    return document

def update_document_status(db: Session, document_id: int, status: str):
    document = db.query(Document).filter(Document.id == document_id).first()
    if document:
        document.status = status
        db.commit()
        db.refresh(document)
    return document

def update_document_file_size(db: Session, document_id: int, file_size: int):
    document = db.query(Document).filter(Document.id == document_id).first()
    if document:
        document.file_size = file_size
        db.commit()
        db.refresh(document)
    return document
