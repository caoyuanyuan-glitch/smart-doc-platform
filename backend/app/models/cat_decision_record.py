from sqlalchemy import Column, Integer, String, DateTime, Text, Float, ForeignKey
from app.database import Base
from datetime import datetime


class CatDecisionRecord(Base):
    __tablename__ = "cat_decision_record"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("cat_analysis_session.id"), index=True, nullable=True)
    analyze_id = Column(String(64), index=True)
    paragraph_index = Column(Integer)
    sentence_index = Column(Integer)
    action = Column(String(20))
    original_text = Column(Text)
    replacement_text = Column(Text)
    category = Column(String(50))
    string_score = Column(Float, default=0.0)
    semantic_score = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
