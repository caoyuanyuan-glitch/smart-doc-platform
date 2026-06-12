from sqlalchemy import Column, Integer, String, DateTime
from app.database import Base
from datetime import datetime

class Term(Base):
    __tablename__ = "terms"
    
    id = Column(Integer, primary_key=True, index=True)
    non_standard = Column(String)
    standard = Column(String)
    category = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
