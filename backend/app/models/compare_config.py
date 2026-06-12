from sqlalchemy import Column, Integer, Float, DateTime, Text
from app.database import Base
from datetime import datetime

class CompareConfig(Base):
    __tablename__ = "compare_configs"
    
    id = Column(Integer, primary_key=True, index=True)
    threshold = Column(Float, default=0.8)
    alpha = Column(Float, default=0.6)
    beta = Column(Float, default=0.4)
    tolerance = Column(Float, default=0.01)
    whitelist = Column(Text, default="[]")
    updated_at = Column(DateTime, default=datetime.utcnow)
