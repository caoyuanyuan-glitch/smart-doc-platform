from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from app.database import Base


class CatDiagnoseRecordLab(Base):
    __tablename__ = "cat_diagnose_record_lab"

    id = Column(Integer, primary_key=True, index=True)
    analyze_id = Column(String(64), index=True, nullable=True)
    source = Column(String(20), default="text")
    sentence_index = Column(Integer, nullable=True)
    original_text = Column(Text)
    quote = Column(Text)
    category = Column(String(50))
    severity = Column(String(20))
    problem = Column(Text)
    revised = Column(Text)
    rationale = Column(Text)
    ruleable = Column(Boolean, default=False, index=True)
    rule_hint = Column(Text, nullable=True)
    status = Column(String(20), default="pending", index=True)
    imported_rule_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
