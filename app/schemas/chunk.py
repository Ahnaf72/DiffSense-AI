from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import SourceType


class ChunkCreate(BaseModel):
    source_type: SourceType
    source_id: UUID
    chunk_index: int
    content: str
    token_count: int = 0
    document_id: UUID | None = None
    reference_id: UUID | None = None


class ChunkResponse(BaseModel):
    id: UUID
    source_type: SourceType
    source_id: UUID
    chunk_index: int
    content: str
    token_count: int
    document_id: UUID | None
    reference_id: UUID | None
    created_at: datetime | None

    model_config = {"from_attributes": True}


class ChunkWithEmbedding(ChunkResponse):
    """Includes embedding vector — used internally, not exposed via API."""
    embedding: list[float] | None = None
