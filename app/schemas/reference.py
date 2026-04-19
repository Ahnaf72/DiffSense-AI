from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ReferenceCreate(BaseModel):
    title: str
    filename: str
    file_path: str
    file_size: int = 0


class ReferenceUpdate(BaseModel):
    title: str | None = None
    is_active: bool | None = None


class ReferenceResponse(BaseModel):
    id: UUID
    title: str
    filename: str
    file_path: str
    file_size: int
    uploaded_by: UUID
    is_active: bool
    created_at: str | datetime
    updated_at: str | datetime

    model_config = {"from_attributes": True}
