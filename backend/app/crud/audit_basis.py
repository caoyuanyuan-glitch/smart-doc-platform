from sqlalchemy.orm import Session
from app.models.audit_basis import AuditBasis
from app.schemas.audit_basis import AuditBasisCreate

def create_audit_basis(db: Session, audit_basis: AuditBasisCreate):
    db_basis = AuditBasis(
        name=audit_basis.name,
        content=audit_basis.content,
        file_type=audit_basis.file_type
    )
    db.add(db_basis)
    db.commit()
    db.refresh(db_basis)
    return db_basis

def get_audit_basis(db: Session, basis_id: int):
    return db.query(AuditBasis).filter(AuditBasis.id == basis_id).first()

def get_audit_bases(db: Session, skip: int = 0, limit: int = 100):
    return db.query(AuditBasis).offset(skip).limit(limit).all()

def delete_audit_basis(db: Session, basis_id: int):
    basis = db.query(AuditBasis).filter(AuditBasis.id == basis_id).first()
    if basis:
        db.delete(basis)
        db.commit()
    return basis
