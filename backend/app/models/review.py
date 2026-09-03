from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from app.database import Base
from datetime import datetime

class Review(Base):
    __tablename__ = "reviews"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="RESTRICT"), nullable=False, index=True)
    mode = Column(String)
    provider = Column(String, nullable=True)
    status = Column(String, default="pending")
    total_issues = Column(Integer, default=0)
    summary = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    stage = Column(String, default="")
    progress = Column(Integer, default=0)
    message = Column(Text, default="")
    heartbeat_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    worker_id = Column(String, nullable=True)
    started_at = Column(DateTime, nullable=True)
    filter_mode = Column(String, default="pipeline")
    visual_document_id = Column(Integer, nullable=True)
    pairing_confirmed = Column(Boolean, default=False)
    pairing_status = Column(String, nullable=True)
    pairing_confidence = Column(Integer, nullable=True)
    input_mode = Column(String, nullable=True)
    error_code = Column(String, nullable=True)
