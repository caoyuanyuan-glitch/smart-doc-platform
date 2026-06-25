from sqlalchemy.orm import Session
from app.models.term import Term
from app.schemas.term import TermCreate, TermUpdate

def create_term(db: Session, term: TermCreate):
    db_term = Term(
        non_standard=term.non_standard,
        standard=term.standard,
        category=term.category
    )
    db.add(db_term)
    db.commit()
    db.refresh(db_term)
    return db_term

def get_term(db: Session, term_id: int):
    return db.query(Term).filter(Term.id == term_id).first()

def get_terms(db: Session, skip: int = 0, limit: int = 100):
    return db.query(Term).offset(skip).limit(limit).all()

def update_term(db: Session, term_id: int, term_update: TermUpdate):
    term = db.query(Term).filter(Term.id == term_id).first()
    if term:
        if term_update.standard is not None:
            term.standard = term_update.standard
        if term_update.category is not None:
            term.category = term_update.category
        db.commit()
        db.refresh(term)
    return term

def delete_term(db: Session, term_id: int):
    term = db.query(Term).filter(Term.id == term_id).first()
    if term:
        db.delete(term)
        db.commit()
    return term

def bulk_create_terms(db: Session, terms: list[TermCreate]):
    db_terms = []
    for term in terms:
        db_terms.append(Term(
            non_standard=term.non_standard,
            standard=term.standard,
            category=term.category
        ))
    if db_terms:
        db.add_all(db_terms)
        db.commit()
    return len(db_terms)
