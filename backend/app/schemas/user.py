from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class UserBase(BaseModel):
    username: str


class UserCreate(UserBase):
    password: str


class UserCreateWithDetails(BaseModel):
    username: str
    password: str
    display_name: str
    role: str = "user"
    status: str = "active"


class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None


class UserPasswordReset(BaseModel):
    new_password: str


class UserLogin(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    display_name: Optional[str] = ""
    role: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class UserListOut(BaseModel):
    items: List[UserOut]
    total: int


class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserOut


class TokenData(BaseModel):
    username: str | None = None
