from pydantic import BaseModel
from datetime import datetime

class DocumentBase(BaseModel):
    filename: str
    file_type: str

class DocumentCreate(DocumentBase):
    content: str
    preview: str = ""

class Document(DocumentBase):
    id: int
    content: str
    status: str
    preview: str
    user_id: int
    created_at: datetime

    class Config:
        orm_mode = True
