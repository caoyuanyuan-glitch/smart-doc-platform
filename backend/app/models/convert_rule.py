from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text
from app.database import Base
from datetime import datetime


class ConvertRule(Base):
    __tablename__ = "convert_rules"

    id = Column(Integer, primary_key=True, index=True)
    rule_number = Column(String(20), unique=True, nullable=False)
    category = Column(String(50), nullable=False)
    description = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
