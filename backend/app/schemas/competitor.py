from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class CompetitorTaskCreate(BaseModel):
    pass


class CompetitorTask(BaseModel):
    id: int
    file_name: str
    file_size: int
    status: str
    tool_analysis: Optional[str] = None
    readability: Optional[str] = None
    report_md: Optional[str] = None
    error: Optional[str] = None
    user_id: int
    created_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CompetitorTaskSummary(BaseModel):
    """列表页摘要：不含 report_md 全文，降低传输量。"""
    id: int
    file_name: str
    file_size: int
    status: str
    tool_analysis: Optional[str] = None
    readability: Optional[str] = None
    error: Optional[str] = None
    user_id: int
    created_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CompetitorReport(BaseModel):
    """报告响应：{content, format}，与 compare 模块报告接口对齐。"""
    content: str
    format: str
