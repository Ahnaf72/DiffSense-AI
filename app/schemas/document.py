from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import UploadStatus


class DocumentCreate(BaseModel):
    filename: str
    file_path: str
    file_size: int = 0
    mime_type: str = "application/pdf"


class DocumentUpdate(BaseModel):
    upload_status: UploadStatus | None = None


class DocumentResponse(BaseModel):
    id: UUID
    user_id: UUID
    filename: str
    file_path: str
    file_size: int
    mime_type: str
    upload_status: UploadStatus
    created_at: str | datetime
    updated_at: str | datetime

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]
    total: int


class SemanticSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Free-text search query")
    source_type: str = Field("reference", description="Filter: 'reference' or 'upload'")
    match_threshold: float = Field(0.3, ge=0.0, le=1.0, description="Minimum cosine similarity")
    match_count: int = Field(10, ge=1, le=100, description="Maximum results")


class SemanticSearchResult(BaseModel):
    id: str
    source_type: str
    source_id: str
    chunk_index: int
    content: str
    similarity: float


class SemanticSearchResponse(BaseModel):
    query: str
    results: list[SemanticSearchResult]
    total: int
