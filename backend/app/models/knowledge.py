from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float
from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base
from datetime import datetime

class Folder(Base):
    __tablename__ = "folders"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    parent_id = Column(Integer, ForeignKey("folders.id"), nullable=True)
    created_by = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    parent = relationship("Folder", remote_side=[id], backref="children")
    files = relationship("KnowledgeFile", back_populates="folder", cascade="all, delete-orphan")

class KnowledgeFile(Base):
    __tablename__ = "knowledge_files"
    
    id = Column(Integer, primary_key=True, index=True)
    folder_id = Column(Integer, ForeignKey("folders.id"), nullable=True)
    name = Column(String, nullable=False)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_size = Column(Float)
    file_type = Column(String)
    permission = Column(String, default="edit")  # read / edit / download
    edit_scope = Column(String, default="all")  # admin / owner / all
    created_by = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    folder = relationship("Folder", back_populates="files")


class KnowledgeFileCall(Base):
    __tablename__ = "knowledge_file_calls"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, index=True, nullable=False)
    module = Column(String, nullable=False, index=True)
    user_id = Column(Integer, nullable=True, index=True)
    username = Column(String, default="guest")
    duration_ms = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class UserKnowledgeGrant(Base):
    __tablename__ = "user_knowledge_grants"
    __table_args__ = (
        UniqueConstraint("user_id", "folder_id", name="uq_user_folder_grant"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    folder_id = Column(Integer, nullable=False, index=True)
    actions = Column(String, nullable=False, default="")
    granted_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
