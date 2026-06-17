from sqlalchemy import Column, Integer, String, DateTime, Text
from app.database import Base
from datetime import datetime

class ConvertTask(Base):
    __tablename__ = "convert_tasks"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(String, unique=True, index=True)
    source_filename = Column(String)
    source_format = Column(String)
    target_format = Column(String)
    template_filename = Column(String, nullable=True)
    requirements = Column(Text, nullable=True)
    status = Column(String, default="processing")
    progress = Column(Integer, default=0)
    current_step = Column(String, nullable=True)
    output_zip_path = Column(String, nullable=True)
    output_size = Column(Integer, nullable=True)
    topic_count = Column(Integer, nullable=True)
    image_count = Column(Integer, nullable=True)
    verification_report = Column(Text, nullable=True)
    conversion_detail = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    retry_feedback = Column(Text, nullable=True)
    retry_screenshot_path = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
