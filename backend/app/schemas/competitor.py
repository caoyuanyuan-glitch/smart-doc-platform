from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime


# ========== 竞品相关 ==========

class CompetitorBase(BaseModel):
    """竞品基础信息"""
    name: str
    brand: Optional[str] = None
    website: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[str] = None


class CompetitorCreate(CompetitorBase):
    """创建竞品"""
    pass


class CompetitorUpdate(BaseModel):
    """更新竞品"""
    name: Optional[str] = None
    brand: Optional[str] = None
    website: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[str] = None


class CompetitorResponse(CompetitorBase):
    """竞品响应"""
    id: int
    user_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    document_count: int = 0

    class Config:
        from_attributes = True


class CompetitorListResponse(BaseModel):
    """竞品列表响应"""
    total: int
    items: List[CompetitorResponse]


# ========== 文档相关 ==========

class CompetitorDocumentBase(BaseModel):
    """文档基础信息"""
    doc_type: str  # competitor / ours
    version: Optional[str] = None
    notes: Optional[str] = None


class CompetitorDocumentCreate(CompetitorDocumentBase):
    """创建文档"""
    pass


class CompetitorDocumentResponse(CompetitorDocumentBase):
    """文档响应"""
    id: int
    competitor_id: int
    file_name: str
    file_path: str
    file_type: Optional[str] = None
    file_size: int = 0
    upload_date: datetime

    class Config:
        from_attributes = True


class CompetitorDocumentListResponse(BaseModel):
    """文档列表响应"""
    competitor_docs: List[CompetitorDocumentResponse]
    our_docs: List[CompetitorDocumentResponse]


# ========== 对比任务相关 ==========

class CompetitorCompareCreate(BaseModel):
    """创建对比任务"""
    competitor_doc_id: int
    our_doc_id: int


class CompetitorCompareTaskResponse(BaseModel):
    """对比任务响应"""
    id: int
    competitor_id: int
    competitor_doc_id: int
    our_doc_id: int
    competitor_doc_name: Optional[str] = None
    our_doc_name: Optional[str] = None
    status: str
    similarity: Optional[float] = None
    result_data: Optional[Any] = None
    suggestions: Optional[Any] = None
    error_message: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CompetitorCompareTaskListResponse(BaseModel):
    """对比任务列表响应"""
    total: int
    items: List[CompetitorCompareTaskResponse]


# ========== 对比结果相关 ==========

class StructureDiffItem(BaseModel):
    """章节结构差异项"""
    section: str
    status: str  # match / similar / competitor_only / ours_only
    competitor_name: Optional[str] = None
    our_name: Optional[str] = None


class ContentDiffItem(BaseModel):
    """内容差异项"""
    section: str
    type: str  # competitor_only / ours_only / content_diff
    content: Optional[str] = None
    detail: Optional[str] = None


class ChapterSimilarity(BaseModel):
    """章节相似度"""
    chapter: str
    similarity: float


class CompareResultData(BaseModel):
    """对比结果数据"""
    structure_diff: List[StructureDiffItem] = []
    content_diff: List[ContentDiffItem] = []
    chapter_similarity: List[ChapterSimilarity] = []


# ========== AI建议相关 ==========

class SuggestionItem(BaseModel):
    """改进建议项"""
    category: str  # 内容补充 / 结构优化 / 参数对标 / 文案优化
    content: str
    reason: str
    reference: Optional[str] = None
    priority: str  # 高 / 中 / 低


class SuggestionsResponse(BaseModel):
    """改进建议响应"""
    suggestions: List[SuggestionItem]
    generated_at: datetime