from sqlalchemy import Column, Integer, String, DateTime, Text, BigInteger
from app.database import Base
from datetime import datetime

class Document(Base):
    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String)
    file_type = Column(String)
    file_size = Column(BigInteger, default=0)
    content = Column(Text)
    status = Column(String, default="pending")
    preview = Column(Text)
    user_id = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
