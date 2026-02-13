from datetime import datetime, timedelta
from typing import Optional, Union
import jwt # [FIX] python-jose -> PyJWT
from passlib.context import CryptContext
from app.core import config

JWTError = jwt.PyJWTError # [FIX] Compatibility for auth endpoints

def _build_pwd_context() -> CryptContext:
    try:
        from passlib.handlers.argon2 import argon2 as argon2_handler
        has_argon2 = bool(argon2_handler.has_backend())
    except Exception:
        has_argon2 = False
    schemes = ["argon2", "bcrypt"] if has_argon2 else ["bcrypt"]
    return CryptContext(schemes=schemes, deprecated="auto")


pwd_context = _build_pwd_context()

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, config.SECRET_KEY, algorithm=config.ALGORITHM)
    return encoded_jwt
