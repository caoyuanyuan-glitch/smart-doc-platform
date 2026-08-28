from sqlalchemy import Column, Integer, String, DateTime, Text
from app.database import Base
from datetime import datetime


class PolishFeedbackLab(Base):
    __tablename__ = "polish_feedback_lab"

    id = Column(Integer, primary_key=True, index=True)
    original_text = Column(Text)
    polished_text = Column(Text)
    accuracy = Column(Integer)
    corrections = Column(Text)
    target = Column(String(50))
    processed_count = Column(Integer, default=0)
    correction_items = Column(Text, nullable=True)
    polish_session_id = Column(String(64), index=True, nullable=True)
    created_by = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
