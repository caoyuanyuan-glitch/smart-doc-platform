from sqlalchemy import Column, Integer, String, DateTime, Text, Float
from app.database import Base
from datetime import datetime


class PolishedDocumentLab(Base):
    __tablename__ = "polished_documents_lab"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_size = Column(Float)
    file_type = Column(String)
    original_content = Column(Text, nullable=True)
    polished_content = Column(Text, nullable=True)
    report_filename = Column(String, nullable=True)
    report_file_path = Column(String, nullable=True)
    folder_id = Column(Integer, nullable=True)
    created_by = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
