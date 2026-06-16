from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class ConvertTaskCreate(BaseModel):
    source_filename: str
    source_format: str
    target_format: str
    template_filename: Optional[str] = None
    requirements: Optional[str] = None


class ConvertTaskOut(BaseModel):
    id: int
    task_id: str
    source_filename: str
    source_format: str
    target_format: str
    template_filename: Optional[str] = None
    requirements: Optional[str] = None
    status: str
    progress: int
    current_step: Optional[str] = None
    topic_count: Optional[int] = None
    image_count: Optional[int] = None
    output_size: Optional[int] = None
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class StepStatus(BaseModel):
    name: str
    status: str


class ProgressOut(BaseModel):
    task_id: str
    status: str
    progress: int
    current_step: Optional[str] = None
    steps: List[StepStatus] = []


class CheckItem(BaseModel):
    name: str
    status: str
    detail: Optional[str] = None


class ReportOut(BaseModel):
    task_id: str
    overall: str
    checks: List[CheckItem] = []
    unmapped_sections: Optional[List[dict]] = None


class ConversionDetail(BaseModel):
    source_section: str
    target_type: str
    topic_file: str
    status: str
