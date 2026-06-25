from pydantic import BaseModel
from typing import Optional


class QaFeedbackCreate(BaseModel):
    question: str
    answer: str
    rating: int = 0
    feedback_text: str = ""


class QaFeedbackOut(BaseModel):
    id: int
    question: str
    answer: str
    rating: int
    feedback_text: str
    resolved: bool
    created_at: Optional[str] = None

    class Config:
        from_attributes = True
