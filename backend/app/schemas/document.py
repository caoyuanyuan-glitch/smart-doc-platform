from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class DocumentBase(BaseModel):
    filename: str
    file_type: str

class DocumentCreate(DocumentBase):
    content: str
    preview: str = ""

class DocumentListItem(BaseModel):
    id: int
    filename: str
    file_type: str
    file_size: Optional[int] = 0
    status: str
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True

class Document(DocumentBase):
    id: int
    content: str
    status: str
    preview: str
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True
