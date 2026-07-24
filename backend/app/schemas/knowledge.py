from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

# Folder schemas
class FolderBase(BaseModel):
    name: str
    parent_id: Optional[int] = None

class FolderCreate(FolderBase):
    pass

class FolderUpdate(BaseModel):
    name: Optional[str] = None

class FolderMove(BaseModel):
    parent_id: Optional[int] = None

class FolderResponse(FolderBase):
    id: int
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class FolderTreeResponse(FolderResponse):
    children: List['FolderTreeResponse'] = []
    files: List['FileResponse'] = []

# File schemas
class FileBase(BaseModel):
    name: str
    folder_id: Optional[int] = None

class FileCreate(FileBase):
    pass

class FileMove(BaseModel):
    folder_id: int

class FileResponse(FileBase):
    id: int
    filename: str
    file_path: str
    file_size: Optional[float] = None
    file_type: Optional[str] = None
    permission: Optional[str] = "edit"
    edit_scope: Optional[str] = "all"
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class FileContentRequest(BaseModel):
    content: str

class FilePermissionRequest(BaseModel):
    permission: Optional[str] = None  # read / edit / download
    edit_scope: Optional[str] = None  # admin / owner / all

FolderTreeResponse.model_rebuild()
FolderTreeResponse.model_rebuild()
