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
    provider: Optional[str] = None

class Review(BaseModel):
    id: int
    document_id: int
    document_name: str = ""
    document_file_type: str = ""
    mode: str
    status: str
    total_issues: int
    summary: Optional[str] = ""
    created_at: datetime
    completed_at: Optional[datetime] = None
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
    status: str = "pending"
    providers: Optional[str] = None  # JSON array string: '["qwen","deepseek"]'

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
    providers: Optional[str] = None  # JSON array: ["qwen","deepseek"]

    class Config:
        orm_mode = True

class IssueUpdate(BaseModel):
    status: str


class FalsePositiveMemoryItem(BaseModel):
    id: int
    source_issue_id: int
    signature: str
    rule: str = ""
    category: str = ""
    original_text: str = ""
    created_at: Optional[datetime] = None
    review_id: Optional[int] = None
    document_id: Optional[int] = None
    document_name: str = ""


class FalsePositiveMemoryListResponse(BaseModel):
    items: list[FalsePositiveMemoryItem]
    total: int
