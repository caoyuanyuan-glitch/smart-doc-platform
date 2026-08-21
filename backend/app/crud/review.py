from sqlalchemy import or_
from sqlalchemy.orm import Session
from app.models.review import Review
from app.models.issue import Issue
from app.models.document import Document
from app.models.false_positive_memory import FalsePositiveMemory
from app.schemas.review import ReviewCreate, IssueCreate, IssueUpdate
from datetime import datetime

def create_review(db: Session, review: ReviewCreate):
    db_review = Review(
        document_id=review.document_id,
        mode=review.mode,
        provider=review.provider,
    )
    db.add(db_review)
    db.commit()
    db.refresh(db_review)
    return db_review

def get_review(db: Session, review_id: int):
    return db.query(Review).filter(Review.id == review_id).first()

def get_reviews(db: Session, document_id: int = None, skip: int = 0, limit: int = 100):
    query = db.query(Review)
    if document_id is not None:
        query = query.filter(Review.document_id == document_id)
    return query.order_by(Review.id.desc()).offset(skip).limit(limit).all()

def update_review_status(db: Session, review_id: int, status: str, total_issues: int = 0, summary: str = ""):
    review = db.query(Review).filter(Review.id == review_id).first()
    if review:
        review.status = status
        review.total_issues = total_issues
        review.summary = summary
        if status in {"completed", "failed"}:
            review.completed_at = datetime.utcnow()
        db.commit()
        db.refresh(review)
    return review

def create_issue(db: Session, issue: IssueCreate):
    db_issue = Issue(
        review_id=issue.review_id,
        severity=issue.severity,
        category=issue.category,
        rule=issue.rule,
        chapter=issue.chapter,
        original_text=issue.original_text,
        context=issue.context,
        suggestion=issue.suggestion,
        description=issue.description,
        audit_basis=issue.audit_basis,
        confidence=issue.confidence,
        source=issue.source,
        position=issue.position,
        status=issue.status,
        providers=issue.providers,
    )
    db.add(db_issue)
    db.commit()
    db.refresh(db_issue)
    return db_issue

def get_issues(db: Session, review_id: int):
    return db.query(Issue).filter(Issue.review_id == review_id).all()

def update_issue(db: Session, issue_id: int, issue_update: IssueUpdate):
    issue = db.query(Issue).filter(Issue.id == issue_id).first()
    if issue:
        issue.status = issue_update.status
        db.commit()
        db.refresh(issue)
    return issue


def list_false_positive_memory_signatures(db: Session):
    rows = db.query(FalsePositiveMemory).filter(FalsePositiveMemory.enabled.is_(True)).all()
    return {str(row.signature or '').strip().lower() for row in rows if str(row.signature or '').strip()}


def delete_false_positive_memory_for_issue(db: Session, source_issue_id: int):
    db.query(FalsePositiveMemory).filter(FalsePositiveMemory.source_issue_id == source_issue_id).delete(synchronize_session=False)
    db.commit()


def upsert_false_positive_memory_for_issue(db: Session, issue, signatures: set[str]):
    normalized_signatures = {
        str(signature or '').strip().lower()
        for signature in signatures
        if str(signature or '').strip()
    }
    db.query(FalsePositiveMemory).filter(FalsePositiveMemory.source_issue_id == issue.id).delete(synchronize_session=False)
    for signature in sorted(normalized_signatures):
        db.add(FalsePositiveMemory(
            source_issue_id=issue.id,
            signature=signature,
            rule=str(getattr(issue, 'rule', '') or ''),
            category=str(getattr(issue, 'category', '') or ''),
            original_text=str(getattr(issue, 'original_text', '') or ''),
            enabled=True,
        ))
    db.commit()


def list_false_positive_memory(db: Session, keyword: str = "", skip: int = 0, limit: int = 50):
    query = (
        db.query(FalsePositiveMemory, Issue, Review, Document)
        .outerjoin(Issue, Issue.id == FalsePositiveMemory.source_issue_id)
        .outerjoin(Review, Review.id == Issue.review_id)
        .outerjoin(Document, Document.id == Review.document_id)
    )

    normalized_keyword = str(keyword or "").strip()
    if normalized_keyword:
        like_pattern = f"%{normalized_keyword}%"
        query = query.filter(or_(
            FalsePositiveMemory.signature.ilike(like_pattern),
            FalsePositiveMemory.rule.ilike(like_pattern),
            FalsePositiveMemory.category.ilike(like_pattern),
            FalsePositiveMemory.original_text.ilike(like_pattern),
            Document.filename.ilike(like_pattern),
        ))

    total = query.count()
    rows = (
        query.order_by(FalsePositiveMemory.created_at.desc(), FalsePositiveMemory.id.desc())
        .offset(max(skip, 0))
        .limit(max(1, limit))
        .all()
    )

    items = []
    for memory, issue, review, document in rows:
        items.append({
            "id": memory.id,
            "source_issue_id": memory.source_issue_id,
            "signature": str(memory.signature or ""),
            "rule": str(memory.rule or ""),
            "category": str(memory.category or ""),
            "original_text": str(memory.original_text or ""),
            "created_at": memory.created_at,
            "review_id": getattr(review, "id", None),
            "document_id": getattr(document, "id", None),
            "document_name": str(getattr(document, "filename", "") or ""),
        })
    return items, total


def delete_false_positive_memory_entry(db: Session, memory_id: int):
    entry = db.query(FalsePositiveMemory).filter(FalsePositiveMemory.id == memory_id).first()
    if entry:
        db.delete(entry)
        db.commit()
    return entry

def delete_issue(db: Session, issue_id: int):
    issue = db.query(Issue).filter(Issue.id == issue_id).first()
    if issue:
        db.delete(issue)
        db.commit()
    return issue


def delete_reviews_by_document(db: Session, document_id: int):
    reviews = db.query(Review).filter(Review.document_id == document_id).all()
    if not reviews:
        return 0

    review_ids = [review.id for review in reviews]
    db.query(Issue).filter(Issue.review_id.in_(review_ids)).delete(synchronize_session=False)
    db.query(Review).filter(Review.id.in_(review_ids)).delete(synchronize_session=False)
    db.commit()
    return len(review_ids)
