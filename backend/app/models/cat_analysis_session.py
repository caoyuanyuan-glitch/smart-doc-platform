from sqlalchemy import Column, Integer, String, DateTime, Float, Text
from app.database import Base
from datetime import datetime


class CatAnalysisSession(Base):
    __tablename__ = "cat_analysis_session"

    id = Column(Integer, primary_key=True, index=True)
    analyze_id = Column(String(64), index=True)
    source_filename = Column(String(255))
    sentence_file_id = Column(Integer, nullable=True)
    sentence_file_name = Column(String(255), nullable=True, index=True)
    total_paragraphs = Column(Integer, default=0)
    total_items = Column(Integer, default=0)
    accepted = Column(Integer, default=0)
    rejected = Column(Integer, default=0)
    modified = Column(Integer, default=0)
    pending = Column(Integer, default=0)
    accuracy_rate = Column(Float, nullable=True)
    rejection_rate = Column(Float, nullable=True)
    modification_rate = Column(Float, nullable=True)
    template_coverage = Column(Float, nullable=True)
    category_summary = Column(Text, nullable=True)
    created_by = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
