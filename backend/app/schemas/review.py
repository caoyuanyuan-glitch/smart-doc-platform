from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class ReviewProgress(BaseModel):
    status: str = "unknown"
    step: str = ""
    progress: int = 0
    message: str = ""
    timestamp: str = ""

class ReviewJudgmentStats(BaseModel):
    confirmed: int = 0
    false_positive: int = 0
    pending: int = 0
    manual: int = 0

class ReviewCreate(BaseModel):
    document_id: int
    mode: str = "hybrid"
    provider: Optional[str] = None
    visual_document_id: Optional[int] = None
    pairing_confirmed: bool = False

class SnippetReviewCreate(BaseModel):
    text: str
    mode: str = "hybrid"
    provider: Optional[str] = None
    force: bool = True

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
    judgment_stats: Optional[ReviewJudgmentStats] = None

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


class PositionObject(BaseModel):
    start: int = 0
    end: int = 0
    area: str = ""
    page: Optional[int] = None


class VisualVerification(BaseModel):
    visual_status: str = "skipped"
    provider: str = ""
    reason: str = ""
    attempts: int = 0
    status: str = "skipped"
    error_code: Optional[str] = None
    verified_at: Optional[str] = None
    evidence_page: Optional[int] = None


class StageDiagnostics(BaseModel):
    stage: str
    input_count: int = 0
    output_count: int = 0
    dropped_count: int = 0
    duration_ms: int = 0
    errors: list[str] = []
    drop_reasons: dict[str, int] = {}


class BasisTrace(BaseModel):
    basis_source: str = "none"
    basis_signature: str = ""
    basis_labels: list[str] = []
    basis_version: str = "review-basis-v1"
    es_available: bool = False
    fallback: bool = False
    fallback_reason: str = ""
    review_id: Optional[int] = None
    issue_id: Optional[int] = None
    candidate_id: Optional[str] = None
    rule_id: str = ""
    basis_query: str = ""
    basis_documents: list[str] = []
    provider: str = ""
    created_at: Optional[str] = None
    status: str = "empty"


class IssueV2(Issue):
    schema_version: str = "v2"
    position_object: Optional[PositionObject] = None
    providers_list: Optional[list[str]] = None
    visual_verification: Optional[VisualVerification] = None
