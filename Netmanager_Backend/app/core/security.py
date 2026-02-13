from datetime import datetime, timedelta
from typing import Optional, Union
import jwt # [FIX] python-jose -> PyJWT
from passlib.context import CryptContext
from app.core import config

JWTError = jwt.PyJWTError # [FIX] Compatibility for auth endpoints

# [UPGRADE] bcrypt -> argon2 (2015 PHC 우승, OWASP 권장, 상용 표준)
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

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
