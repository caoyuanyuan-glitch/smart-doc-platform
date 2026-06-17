from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class ReviewProgress(BaseModel):
    status: str = "unknown"
    step: str = ""
    progress: int = 0
    message: str = ""
    timestamp: str = ""

class ReviewCreate(BaseModel):
    document_id: int
    mode: str = "hybrid"

class Review(BaseModel):
    id: int
    document_id: int
    document_name: str = ""
    mode: str
    status: str
    total_issues: int
    summary: str
    created_at: datetime
    progress: Optional[ReviewProgress] = None

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
