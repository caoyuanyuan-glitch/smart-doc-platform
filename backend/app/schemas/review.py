from pydantic import BaseModel
from datetime import datetime

class ReviewCreate(BaseModel):
    document_id: int
    mode: str = "hybrid"

class Review(BaseModel):
    id: int
    document_id: int
    mode: str
    status: str
    total_issues: int
    summary: str
    created_at: datetime

    class Config:
        orm_mode = True

class IssueCreate(BaseModel):
    review_id: int
    severity: str
    category: str
    rule: str
    chapter: str
    original_text: str
    context: str = ""
    suggestion: str = ""
    description: str = ""
    audit_basis: str = ""
    confidence: int = 0
    source: str = "rule"
    position: str = "{}"

class Issue(BaseModel):
    id: int
    review_id: int
    severity: str
    category: str
    rule: str
    chapter: str
    original_text: str
    context: str
    suggestion: str
    description: str
    audit_basis: str
    confidence: int
    source: str
    status: str
    position: str

    class Config:
        orm_mode = True

class IssueUpdate(BaseModel):
    status: str
