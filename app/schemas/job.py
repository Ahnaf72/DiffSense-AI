from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class JobSubmitResponse(BaseModel):
    """Returned when a job is enqueued."""
    job_id: str
    doc_id: str
    state: str = "PENDING"


class JobProgressInfo(BaseModel):
    step: str
    current: int
    total: int
    doc_id: str


class JobStatusResponse(BaseModel):
    """Full job status for polling."""
    job_id: str
    state: str
    doc_id: str | None = None
    progress: JobProgressInfo | None = None
    result: dict | None = None
    error: str | None = None

    model_config = {"from_attributes": True}
