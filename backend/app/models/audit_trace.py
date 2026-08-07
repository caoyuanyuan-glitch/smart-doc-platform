from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.database import Base


class AuditTrace(Base):
    __tablename__ = "audit_trace"

    id = Column(Integer, primary_key=True, index=True)
    review_id = Column(Integer, index=True, nullable=False)
    chunk_index = Column(Integer, default=0)
    chunk_size = Column(Integer, default=0)
    provider = Column(String, default="")
    model = Column(String, default="")
    request_label = Column(String, default="")
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    latency_ms = Column(Integer, nullable=True)
    status = Column(String, default="success")
    error_message = Column(Text, nullable=True)
    parsed_issue_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
