"""
auth_service.py  ─  Authentication & JWT token management
=========================================================
Handles password hashing, JWT creation/verification,
and user authentication against the Supabase database.
"""

from datetime import datetime, timedelta
from typing import Optional

from passlib.context import CryptContext
from jose import JWTError, jwt

from backend.config import config
from backend.db.supabase_client import db

# ── Password hashing ──────────────────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


# ── JWT tokens ────────────────────────────────────────────────────────────
def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    payload = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(
        minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES))
    payload.update({"exp": expire})
    return jwt.encode(payload, config.SECRET_KEY, algorithm=config.ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """Decode a JWT token and return the payload, or None if invalid."""
    try:
        payload = jwt.decode(token, config.SECRET_KEY, algorithms=[config.ALGORITHM])
        return payload
    except JWTError:
        return None


# ── User authentication ──────────────────────────────────────────────────
def authenticate_user(username: str, password: str) -> Optional[dict]:
    """
    Verify credentials against the Supabase users table.
    Returns the user dict on success, None on failure.
    """
    user = db.get_user_by_username(username)
    if not user:
        return None
    if not verify_password(password, user.get("hashed_password", "")):
        return None
    return user


def get_current_user_from_token(token: str) -> dict:
    """
    Decode a JWT token and fetch the user from the database.
    Raises ValueError if the token is invalid or user not found.
    """
    payload = decode_token(token)
    if payload is None:
        raise ValueError("Invalid token")
    username = payload.get("sub")
    if not username:
        raise ValueError("Invalid token payload")
    user = db.get_user_by_username(username)
    if user is None:
        raise ValueError("User not found")
    return user


def change_password(username: str, current_password: str, new_password: str) -> bool:
    """Change a user's password. Returns True on success."""
    user = db.get_user_by_username(username)
    if not user:
        return False
    if not verify_password(current_password, user.get("hashed_password", "")):
        return False
    new_hash = hash_password(new_password)
    db.update_user(username, {"hashed_password": new_hash})
    return True
