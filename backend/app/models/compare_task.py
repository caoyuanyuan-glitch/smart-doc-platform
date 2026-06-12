from sqlalchemy import Column, Integer, String, DateTime, Float, Text
from app.database import Base
from datetime import datetime

class CompareTask(Base):
    __tablename__ = "compare_tasks"
    
    id = Column(Integer, primary_key=True, index=True)
    file_a_name = Column(String)
    file_b_name = Column(String)
    similarity = Column(Float)
    verdict = Column(String)
    total_diffs = Column(Integer)
    diff_stats = Column(Text)
    status = Column(String, default="pending")
    user_id = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
