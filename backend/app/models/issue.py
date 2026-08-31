from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from app.database import Base
from datetime import datetime

class Issue(Base):
    __tablename__ = "issues"
    
    id = Column(Integer, primary_key=True, index=True)
    review_id = Column(Integer, ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False, index=True)
    severity = Column(String)
    category = Column(String)
    rule = Column(String)
    chapter = Column(String)
    original_text = Column(Text)
    context = Column(Text)
    suggestion = Column(Text)
    description = Column(Text)
    audit_basis = Column(Text)
    confidence = Column(Integer)
    source = Column(String)
    status = Column(String, default="pending")
    position = Column(Text)
    providers = Column(Text, nullable=True)  # JSON array: ["qwen","deepseek"] — 多模型交叉验证
    created_at = Column(DateTime, default=datetime.utcnow)
