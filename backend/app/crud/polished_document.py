from sqlalchemy.orm import Session
from app.models.polished_document import PolishedDocument

def get_polished_documents(db: Session, skip: int = 0, limit: int = 100):
    return db.query(PolishedDocument).order_by(PolishedDocument.created_at.desc()).offset(skip).limit(limit).all()

def get_polished_document(db: Session, doc_id: int):
    return db.query(PolishedDocument).filter(PolishedDocument.id == doc_id).first()

def create_polished_document(db: Session, name: str, filename: str, file_path: str, file_size: float, file_type: str, original_content: str = None, polished_content: str = None, created_by: int = None, report_filename: str = None, report_file_path: str = None, folder_id: int = None):
    db_doc = PolishedDocument(
        name=name,
        filename=filename,
        file_path=file_path,
        file_size=file_size,
        file_type=file_type,
        original_content=original_content,
        polished_content=polished_content,
        report_filename=report_filename,
        report_file_path=report_file_path,
        folder_id=folder_id,
        created_by=created_by
    )
    db.add(db_doc)
    db.commit()
    db.refresh(db_doc)
    return db_doc

def update_polished_content(db: Session, doc_id: int, polished_content: str):
    doc = get_polished_document(db, doc_id)
    if doc:
        doc.polished_content = polished_content
        db.commit()
        db.refresh(doc)
    return doc

def delete_polished_document(db: Session, doc_id: int):
    doc = get_polished_document(db, doc_id)
    if doc:
        db.delete(doc)
        db.commit()
    return doc
