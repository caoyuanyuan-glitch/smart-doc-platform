from pydantic import BaseModel
from datetime import datetime

class AuditBasisCreate(BaseModel):
    name: str
    content: str
    file_type: str

class AuditBasis(BaseModel):
    id: int
    name: str
    content: str
    file_type: str
    created_at: datetime

    class Config:
        orm_mode = True
