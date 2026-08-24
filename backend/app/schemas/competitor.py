from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List


class CompetitorTaskCreate(BaseModel):
    pass


class CompetitorUrlAnalyzeRequest(BaseModel):
    url: str


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


# ------------------------------------------------------------ 多文档对比

class CompetitorComparisonCreate(BaseModel):
    """创建对比：2-5 个已完成分析任务，可选其一为我方基线。"""
    title: str = ""
    task_ids: List[int] = Field(..., min_length=2, max_length=5)
    baseline_task_id: Optional[int] = None


class CompetitorComparison(BaseModel):
    id: int
    title: str
    task_ids: Optional[str] = None
    baseline_task_id: Optional[int] = None
    result_json: Optional[str] = None
    report_md: Optional[str] = None
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class CompetitorComparisonSummary(BaseModel):
    """对比列表摘要：不含 report_md / result_json 全文。"""
    id: int
    title: str
    task_ids: Optional[str] = None
    baseline_task_id: Optional[int] = None
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True
