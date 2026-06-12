from pydantic import BaseModel
from datetime import datetime

class TermBase(BaseModel):
    non_standard: str
    standard: str
    category: str = ""

class TermCreate(TermBase):
    pass

class Term(TermBase):
    id: int
    created_at: datetime

    class Config:
        orm_mode = True

class TermUpdate(BaseModel):
    standard: str | None = None
    category: str | None = None
