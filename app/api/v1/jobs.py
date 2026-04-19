"""Job status polling endpoints."""

from fastapi import APIRouter, HTTPException, Request, status

from app.schemas.job import JobStatusResponse
from app.core.worker import celery_app

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}/status", response_model=JobStatusResponse)
async def get_job_status(request: Request, job_id: str):
    """Check the status of an async analysis job."""
    # Rate limit: 60 requests per minute per IP
    from app.main import app as _app
    _app.state.limiter.limit("60/minute")(request)

    # Validate job_id format (Celery task IDs are UUID-like)
    if not job_id or len(job_id) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid job_id")

    result = celery_app.AsyncResult(job_id)

    response = JobStatusResponse(job_id=job_id, state=result.state)

    if result.state == "SUCCESS":
        data = result.result or {}
        response.result = data
        response.doc_id = data.get("doc_id")
    elif result.state == "FAILURE":
        response.error = str(result.result)
    elif result.state == "PROGRESS":
        info = result.info or {}
        response.progress = info
        response.doc_id = info.get("doc_id")

    return response
