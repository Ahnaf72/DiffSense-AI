"""
auth_routes.py  ─  Authentication API routes
=============================================
/token           - Login (OAuth2 password flow)
/me              - Get current user info
/change-password - Change password
"""

from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Form
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

from backend.services.auth_service import (
    authenticate_user, create_access_token,
    get_current_user_from_token, change_password,
)
from backend.config import config

router = APIRouter(tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """FastAPI dependency: decode token and return user dict."""
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        user = get_current_user_from_token(token)
        return user
    except ValueError:
        raise exc


@router.post("/token")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """OAuth2 password flow — returns access_token, token_type, role."""
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    token = create_access_token(
        {"sub": user["username"]},
        timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return {"access_token": token, "token_type": "bearer", "role": user["role"]}


@router.get("/me")
def get_me(current_user: dict = Depends(get_current_user)):
    """Return the current authenticated user's info."""
    return {
        "username":  current_user.get("username"),
        "full_name": current_user.get("full_name"),
        "role":      current_user.get("role"),
    }


@router.post("/admin/change-password")
def change_password_endpoint(
    current_password: str = Form(...),
    new_password:     str = Form(...),
    current_user:     dict = Depends(get_current_user),
):
    """Change the current user's password."""
    success = change_password(
        current_user["username"], current_password, new_password)
    if not success:
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    return {"message": "Password updated successfully"}
