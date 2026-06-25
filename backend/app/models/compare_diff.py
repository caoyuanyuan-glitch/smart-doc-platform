from sqlalchemy import Column, Integer, String, Float, Text
from app.database import Base

class CompareDiff(Base):
    __tablename__ = "compare_diffs"
    
    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer)
    diff_type = Column(String)
    severity = Column(String)
    similarity = Column(Float)
    text_a = Column(Text)
    text_b = Column(Text)
    position_a = Column(Text)
    position_b = Column(Text)
    chapter = Column(String)
