from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text
from app.database import Base
from datetime import datetime


class QaFeedback(Base):
    __tablename__ = "qa_feedbacks"

    id = Column(Integer, primary_key=True, index=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    rating = Column(Integer, default=0)
    feedback_text = Column(Text, default="")
    resolved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
