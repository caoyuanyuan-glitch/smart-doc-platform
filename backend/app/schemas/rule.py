from pydantic import BaseModel
from datetime import datetime

class RuleBase(BaseModel):
    rule_no: str
    category: str
    description: str
    regex: str
    example: str = ""
    suggestion: str = ""
    audit_basis: str = ""
    language: str = "both"  # cn, en, both

class RuleCreate(RuleBase):
    pass

class Rule(RuleBase):
    id: int
    created_at: datetime

    class Config:
        orm_mode = True

class RuleUpdate(BaseModel):
    category: str | None = None
    description: str | None = None
    regex: str | None = None
    example: str | None = None
    suggestion: str | None = None
    audit_basis: str | None = None
    language: str | None = None