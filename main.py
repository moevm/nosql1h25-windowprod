from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import jwt
from datetime import datetime, timedelta
import os
from typing import Optional
from .db import db
from fastapi import Request

app = FastAPI(title="WindowShop", description="Система заказов оконных конструкций")
templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Конфигурация JWT
SECRET_KEY = os.getenv("SECRET_KEY", "secret-key-123")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

class TokenData(BaseModel):
    username: str
    role: str
    exp: Optional[datetime] = None

class User(BaseModel):
    username: str
    role: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    id: Optional[str] = None

class ProductFilters(BaseModel):
    name: Optional[str] = None
    material: Optional[str] = None
    color: Optional[str] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    min_width: Optional[float] = None
    max_width: Optional[float] = None
    min_height: Optional[float] = None
    max_height: Optional[float] = None
    in_stock: Optional[bool] = None


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(request: Request) -> Optional[User]:
    token = request.cookies.get("access_token")
    if not token:
        return None
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role")
        if username is None:
            return None
        
        user_data = db.collection("users").find({"username": username}).next()
        return User(
            username=username,
            role=role,
            first_name=user_data.get("first_name"),
            last_name=user_data.get("last_name"),
            id=user_data.get("_key")
        )
    except Exception as e:
        print(f"Ошибка декодирования токена: {e}")
        return None