from sqlalchemy import Column, Integer, String, DateTime, Float, Text
from app.database import Base
from datetime import datetime

class CompareTask(Base):
    __tablename__ = "compare_tasks"
    
    id = Column(Integer, primary_key=True, index=True)
    file_a_name = Column(String)
    file_b_name = Column(String)
    file_names = Column(Text)
    group_id = Column(Integer, index=True, nullable=True, default=None)
    similarity = Column(Float)
    verdict = Column(String)
    total_diffs = Column(Integer)
    diff_stats = Column(Text)
    status = Column(String, default="pending")
    user_id = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    exact_match = Column(Integer, default=0)
    n_a = Column(Integer, default=0)
    n_b = Column(Integer, default=0)
    matched_pairs = Column(Text)
    only_a = Column(Text)
    only_b = Column(Text)
    dita_full = Column(Text)
