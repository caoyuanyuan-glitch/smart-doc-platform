from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from app.database import Base


class AuditTrace(Base):
    __tablename__ = "audit_traces"

    id = Column(Integer, primary_key=True, index=True)
    review_id = Column(Integer, ForeignKey("reviews.id", ondelete="CASCADE"), index=True, nullable=False)
    request_label = Column(String, default="generic")
    chunk_index = Column(Integer, nullable=True)
    chunk_size = Column(Integer, default=0)
    provider = Column(String, default="unknown")
    model = Column(String, default="")
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    latency_ms = Column(Integer, default=0)
    status = Column(String, default="ok")
    error_message = Column(Text, nullable=True)
    parsed_issue_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
