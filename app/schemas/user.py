from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import UserRole


# ── Auth ────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    user_id: UUID
    username: str
    role: UserRole


# ── User CRUD ───────────────────────────────────────────────────────

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)
    full_name: str | None = None


class UserUpdate(BaseModel):
    full_name: str | None = None
    password: str | None = Field(None, min_length=6)


class UserResponse(BaseModel):
    id: UUID
    username: str
    role: UserRole
    full_name: str | None
    created_at: str | datetime
    updated_at: str | datetime

    model_config = {"from_attributes": True}


class UserDetailResponse(UserResponse):
    """User with nested relationships (avoid circular — use IDs only)."""
    document_ids: list[UUID] = []
    report_ids: list[UUID] = []
