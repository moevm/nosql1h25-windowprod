from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class UserBase(BaseModel):
    username: str
    first_name: str
    last_name: str
    phone_number: str
    role: str

class UserCreate(UserBase):
    password: str

class UserInDB(UserBase):
    id: str
    is_active: bool
    created_at: datetime

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None
    role: Optional[str] = None