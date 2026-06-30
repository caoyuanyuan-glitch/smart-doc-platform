from datetime import datetime
from typing import Optional, Literal

from pydantic import BaseModel

RuleType = Literal["system_rule", "replacement_rule", "forbidden_rule", "sentence_applicability_rule"]


class PolishLearningRuleBase(BaseModel):
    rule_name: Optional[str] = None
    rule_type: RuleType
    engine_key: Optional[str] = None
    rule_key: str
    match_pattern: str
    replacement_text: Optional[str] = None
    description: Optional[str] = None
    priority_level: int = 0
    enabled: bool = True


class PolishLearningRuleCreate(PolishLearningRuleBase):
    pass


class PolishLearningRuleUpdate(BaseModel):
    rule_name: Optional[str] = None
    rule_type: Optional[RuleType] = None
    engine_key: Optional[str] = None
    rule_key: Optional[str] = None
    match_pattern: Optional[str] = None
    replacement_text: Optional[str] = None
    description: Optional[str] = None
    priority_level: Optional[int] = None
    enabled: Optional[bool] = None


class PolishLearningRuleOut(PolishLearningRuleBase):
    id: int
    trigger_count: int
    last_triggered_at: Optional[datetime] = None
    source_feedback_id: Optional[int] = None
    knowledge_file_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PolishLearningRuleBatchImport(BaseModel):
    rules: list[PolishLearningRuleCreate]


class PolishLearningRuleBatchDelete(BaseModel):
    ids: list[int]
