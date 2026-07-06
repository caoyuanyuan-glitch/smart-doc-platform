from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Float
from sqlalchemy.orm import relationship
from app.database import Base
from datetime import datetime


class QaSession(Base):
    __tablename__ = "qa_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_type = Column(String(20), nullable=False)
    title = Column(String(200), default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    messages = relationship("QaMessage", back_populates="session", cascade="all, delete-orphan")


class QaMessage(Base):
    __tablename__ = "qa_messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("qa_sessions.id"), nullable=False)
    role = Column(String(16), nullable=False)
    content = Column(Text, nullable=False)
    sources = Column(Text, default="[]")
    rating = Column(Integer, default=0)
    search_hit = Column(Integer, default=0)
    relevance_score = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("QaSession", back_populates="messages")
