from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.crud.term import create_term, get_term, get_terms, update_term, delete_term, bulk_create_terms
from app.schemas.term import Term, TermCreate, TermUpdate

router = APIRouter()

@router.post("/", response_model=Term)
async def create_new_term(term: TermCreate, db: Session = Depends(get_db)):
    return create_term(db=db, term=term)

@router.get("/", response_model=list[Term])
async def read_terms(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    terms = get_terms(db, skip=skip, limit=limit)
    return terms

@router.get("/{term_id}", response_model=Term)
async def read_term(term_id: int, db: Session = Depends(get_db)):
    term = get_term(db, term_id=term_id)
    if not term:
        raise HTTPException(status_code=404, detail="Term not found")
    return term

@router.put("/{term_id}", response_model=Term)
async def update_existing_term(term_id: int, term_update: TermUpdate, db: Session = Depends(get_db)):
    term = update_term(db, term_id=term_id, term_update=term_update)
    if not term:
        raise HTTPException(status_code=404, detail="Term not found")
    return term

@router.delete("/{term_id}")
async def delete_existing_term(term_id: int, db: Session = Depends(get_db)):
    term = delete_term(db, term_id=term_id)
    if not term:
        raise HTTPException(status_code=404, detail="Term not found")
    return {"message": "Term deleted successfully"}

@router.post("/bulk")
async def bulk_create(terms: list[TermCreate], db: Session = Depends(get_db)):
    count = bulk_create_terms(db, terms)
    return {"message": f"Created {count} terms"}
