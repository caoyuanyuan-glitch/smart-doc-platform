from pydantic import BaseModel
from datetime import datetime

class CompareConfig(BaseModel):
    threshold: float = 0.8
    tolerance: float = 0.01

class CompareTaskCreate(BaseModel):
    config: CompareConfig | None = None

class CompareTask(BaseModel):
    id: int
    file_a_name: str
    file_b_name: str
    similarity: float
    verdict: str
    total_diffs: int
    diff_stats: str
    status: str
    user_id: int
    created_at: datetime

    class Config:
        orm_mode = True

class CompareDiff(BaseModel):
    id: int
    task_id: int
    diff_type: str
    severity: str
    similarity: float
    text_a: str
    text_b: str
    position_a: str
    position_b: str
    chapter: str

    class Config:
        orm_mode = True

class CompareResult(BaseModel):
    task_id: int
    similarity: float
    verdict: str
    total_diffs: int
    diff_stats: dict
    diffs: list[CompareDiff]
