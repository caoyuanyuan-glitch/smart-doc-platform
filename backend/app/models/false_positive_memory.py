from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from app.database import Base


class FalsePositiveMemory(Base):
    __tablename__ = "false_positive_memory"

    id = Column(Integer, primary_key=True, index=True)
    source_issue_id = Column(Integer, index=True, nullable=False)
    signature = Column(String(512), index=True, nullable=False)
    rule = Column(String, default="")
    category = Column(String, default="")
    original_text = Column(Text, default="")
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
