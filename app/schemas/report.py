from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ReportStatus


class ReportCreate(BaseModel):
    document_id: UUID


class ReportUpdate(BaseModel):
    overall_score: float | None = None
    total_chunks: int | None = None
    matched_chunks: int | None = None
    status: ReportStatus | None = None
    summary: str | None = None


class ReportResponse(BaseModel):
    id: UUID
    user_id: UUID
    document_id: UUID
    overall_score: float
    total_chunks: int
    matched_chunks: int
    status: ReportStatus
    summary: str | None
    score_breakdown: dict | None = None
    created_at: str | datetime
    updated_at: str | datetime

    model_config = {"from_attributes": True}


class MatchCreate(BaseModel):
    upload_chunk_id: UUID
    reference_chunk_id: UUID
    similarity_score: float = Field(..., ge=0, le=1)
    report_id: UUID | None = None


class MatchResponse(BaseModel):
    id: UUID
    upload_chunk_id: UUID
    reference_chunk_id: UUID
    similarity_score: float
    report_id: UUID | None
    created_at: datetime | None

    model_config = {"from_attributes": True}
