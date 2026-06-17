from sqlalchemy import Column, Integer, String, DateTime, Text
from app.database import Base
from datetime import datetime


class MemoryBank(Base):
    __tablename__ = "memory_bank"

    id = Column(Integer, primary_key=True, index=True)
    source_text = Column(Text, nullable=False)
    translated_text = Column(Text, nullable=False)
    source_lang = Column(String, default="zh")
    target_lang = Column(String, default="en")
    tags = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
