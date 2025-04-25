from .db import db
from datetime import datetime, timedelta
import bcrypt
import jwt
import os

SECRET_KEY = os.getenv("SECRET_KEY", "secret-key-123")
ALGORITHM = "HS256"

def authenticate_user(username: str, password: str):
    """Аутентификация пользователя"""
    if db is None:
        return None
        
    user = db.collection("users").find({"username": username}).next()
    if not user or not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        return None
    return user

def create_access_token(data: dict, expires_delta: timedelta = None):
    """Создание JWT токена"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)