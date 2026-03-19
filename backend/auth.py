"""
auth.py — JWT authentication using python-jose + bcrypt directly
(avoids passlib's deprecated 'crypt' module removed in Python 3.13)
"""
import os
import bcrypt
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db, User

SECRET_KEY         = os.getenv("SECRET_KEY", "cloudscreener-jwt-secret-2025")
ALGORITHM          = "HS256"
TOKEN_EXPIRE_HOURS = 24

oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

class UserRegister(BaseModel):
    name: str
    email: str
    password: str

class UserLogin(BaseModel):
    email: str
    password: str


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False

def create_token(user_id: int, email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)
    return jwt.encode({"sub": str(user_id), "email": email, "exp": expire},
                      SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2), db: Session = Depends(get_db)) -> User:
    exc = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Invalid or expired token. Please log in again.",
                        headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        raise exc
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise exc
    return user

def register_user(data: UserRegister, db: Session) -> dict:
    if db.query(User).filter(User.email == data.email.lower()).first():
        raise HTTPException(400, "Email already registered. Please log in.")
    user = User(name=data.name.strip(), email=data.email.lower().strip(),
                hashed_password=hash_password(data.password))
    db.add(user); db.commit(); db.refresh(user)
    return {"access_token": create_token(user.id, user.email), "token_type": "bearer",
            "user": {"id": user.id, "name": user.name, "email": user.email}}

def login_user(email: str, password: str, db: Session) -> dict:
    user = db.query(User).filter(User.email == email.lower().strip()).first()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(401, "Incorrect email or password.")
    return {"access_token": create_token(user.id, user.email), "token_type": "bearer",
            "user": {"id": user.id, "name": user.name, "email": user.email}}