from sqlalchemy import Column, Integer, String, DateTime, Text
from app.database import Base
from datetime import datetime


class TranslationDoc(Base):
    __tablename__ = "translation_docs"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    file_type = Column(String, default="")
    source_lang = Column(String, default="zh")
    target_lang = Column(String, default="en")
    engine = Column(String, default="ai")
    model = Column(String, default="kimi")
    original_content = Column(Text, default="")
    translated_content = Column(Text, default="")
    translated_filename = Column(String, default="")
    original_preview = Column(Text, default="")
    translated_preview = Column(Text, default="")
    source_char_count = Column(Integer, default=0)
    ai_char_count = Column(Integer, default=0)
    memory_char_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
