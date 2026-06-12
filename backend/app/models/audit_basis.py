from sqlalchemy import Column, Integer, String, DateTime, Text
from app.database import Base
from datetime import datetime

class AuditBasis(Base):
    __tablename__ = "audit_bases"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    content = Column(Text)
    file_type = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
