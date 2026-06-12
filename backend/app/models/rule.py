from sqlalchemy import Column, Integer, String, DateTime, Text
from app.database import Base
from datetime import datetime

class Rule(Base):
    __tablename__ = "rules"
    
    id = Column(Integer, primary_key=True, index=True)
    rule_no = Column(String, unique=True)
    category = Column(String)
    description = Column(Text)
    regex = Column(Text)
    example = Column(Text)
    suggestion = Column(Text)
    audit_basis = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
