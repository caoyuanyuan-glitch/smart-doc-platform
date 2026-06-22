from sqlalchemy import Column, Integer, String, DateTime, Text, Float
from app.database import Base
from datetime import datetime


class PolishFeedback(Base):
    __tablename__ = "polish_feedback"

    id = Column(Integer, primary_key=True, index=True)
    original_text = Column(Text)
    polished_text = Column(Text)
    accuracy = Column(Integer)          # 0-100 准确率评分
    corrections = Column(Text)          # 用户填写的修正内容原始文本
    target = Column(String(50))         # "terminology" | "sentence_guide"
    processed_count = Column(Integer, default=0)  # 成功写入的条目数
    created_by = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
