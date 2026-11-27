from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base


class QaCard(Base):
    __tablename__ = "qa_cards"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, nullable=False, unique=True, index=True)
    kicker = Column(String, nullable=False, default="自定义")
    title = Column(String, nullable=False)
    description = Column(String, nullable=False, default="")
    accent = Column(String, nullable=False, default="#1d4ed8")
    suggestions_json = Column(Text, nullable=False, default="[]")
    home_visible = Column(Boolean, nullable=False, default=True)
    sort_order = Column(Integer, nullable=False, default=0, index=True)
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    folders = relationship("QaCardFolder", back_populates="card", cascade="all, delete-orphan")


class QaCardFolder(Base):
    __tablename__ = "qa_card_folders"
    __table_args__ = (
        UniqueConstraint("card_id", "folder_id", name="uq_qa_card_folder"),
    )

    id = Column(Integer, primary_key=True, index=True)
    card_id = Column(
        Integer,
        ForeignKey("qa_cards.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    folder_id = Column(
        Integer,
        ForeignKey("folders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    card = relationship("QaCard", back_populates="folders")


class QaCardSeedState(Base):
    __tablename__ = "qa_card_seed_state"

    id = Column(Integer, primary_key=True)
    seeded_at = Column(DateTime, default=datetime.utcnow)
