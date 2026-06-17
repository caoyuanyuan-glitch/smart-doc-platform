from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class ConvertRuleCreate(BaseModel):
    rule_number: Optional[str] = None
    category: str
    description: str
    is_active: Optional[bool] = True


class ConvertRuleOut(BaseModel):
    id: int
    rule_number: str
    category: str
    description: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ConvertRulesBulkDelete(BaseModel):
    rule_ids: List[int]
