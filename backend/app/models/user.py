from sqlalchemy import Column, Integer, String, DateTime
from app.database import Base
from datetime import datetime

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password_hash = Column(String)
    display_name = Column(String, default="")
    role = Column(String, default="user")
    status = Column(String, default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
