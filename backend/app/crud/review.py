from sqlalchemy.orm import Session
from app.models.review import Review
from app.models.issue import Issue
from app.schemas.review import ReviewCreate, IssueCreate, IssueUpdate

def create_review(db: Session, review: ReviewCreate):
    db_review = Review(
        document_id=review.document_id,
        mode=review.mode
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
    return query.offset(skip).limit(limit).all()

def update_review_status(db: Session, review_id: int, status: str, total_issues: int = 0, summary: str = ""):
    review = db.query(Review).filter(Review.id == review_id).first()
    if review:
        review.status = status
        review.total_issues = total_issues
        review.summary = summary
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
        position=issue.position
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

def delete_issue(db: Session, issue_id: int):
    issue = db.query(Issue).filter(Issue.id == issue_id).first()
    if issue:
        db.delete(issue)
        db.commit()
    return issue
