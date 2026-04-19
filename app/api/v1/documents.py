import tempfile
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status

from app.core.deps import get_current_user, get_document_service, get_chunk_service
from app.core.exceptions import AppError, ConflictError, NotFoundError, ValidationError, require_owner_or_admin
from app.core.storage import MAX_FILE_SIZE, ensure_upload_dir, validate_extension
from app.schemas.document import DocumentCreate, DocumentListResponse, DocumentResponse, SemanticSearchRequest, SemanticSearchResponse, SemanticSearchResult
from app.schemas.job import JobSubmitResponse
from app.schemas.user import TokenData
from app.services.document_service import DocumentService
from app.services.chunk_service import ChunkService

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=DocumentListResponse)
async def list_my_documents(
    limit: int = 50,
    offset: int = 0,
    current_user: TokenData = Depends(get_current_user),
    svc: DocumentService = Depends(get_document_service),
):
    # Validate pagination parameters
    if limit < 1 or limit > 100:
        raise ValidationError("limit must be between 1 and 100")
    if offset < 0:
        raise ValidationError("offset must be non-negative")
    docs = svc.list_user_documents_paginated(current_user.user_id, limit=limit, offset=offset)
    # Get actual total count for pagination
    total = svc.count_user_documents(current_user.user_id)
    return DocumentListResponse(documents=docs, total=total)


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_pdf(
    file: UploadFile,
    current_user: TokenData = Depends(get_current_user),
    svc: DocumentService = Depends(get_document_service),
):
    """Upload a PDF file. Validates type, saves to disk, stores metadata in DB."""
    if not file.filename:
        raise ValidationError("Filename is required")
    try:
        validate_extension(file.filename)
    except ValueError as e:
        raise ValidationError(str(e))

    ensure_upload_dir()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        file_size = 0
        while chunk := await file.read(1024 * 1024):
            file_size += len(chunk)
            if file_size > MAX_FILE_SIZE:
                Path(tmp.name).unlink(missing_ok=True)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File too large. Max {MAX_FILE_SIZE // (1024*1024)} MB",
                )
            tmp.write(chunk)
        tmp_path = Path(tmp.name)

    try:
        doc = svc.upload_file(
            user_id=current_user.user_id,
            filename=file.filename,
            src_path=tmp_path,
            file_size=file_size,
        )
    except ValueError as e:
        tmp_path.unlink(missing_ok=True)
        raise ValidationError(str(e))
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise AppError("Upload failed")
    return doc


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def create_document_metadata(
    body: DocumentCreate,
    current_user: TokenData = Depends(get_current_user),
    svc: DocumentService = Depends(get_document_service),
):
    """Create document metadata only (no file upload)."""
    return svc.upload_document(
        current_user.user_id, body.filename, body.file_path, body.file_size, body.mime_type
    )


@router.get("/{doc_id}", response_model=DocumentResponse)
async def get_document(
    doc_id: UUID,
    current_user: TokenData = Depends(get_current_user),
    svc: DocumentService = Depends(get_document_service),
):
    doc = svc.get_document(doc_id)
    if not doc:
        raise NotFoundError("Document not found")
    require_owner_or_admin(doc["user_id"], current_user.user_id, current_user.role)
    return doc


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    doc_id: UUID,
    current_user: TokenData = Depends(get_current_user),
    svc: DocumentService = Depends(get_document_service),
):
    doc = svc.get_document(doc_id)
    if not doc:
        raise NotFoundError("Document not found")
    require_owner_or_admin(doc["user_id"], current_user.user_id, current_user.role)
    svc.delete_document(doc_id)


@router.post("/{doc_id}/analyze", response_model=JobSubmitResponse, status_code=status.HTTP_202_ACCEPTED)
async def analyze_document(
    doc_id: UUID,
    current_user: TokenData = Depends(get_current_user),
    svc: DocumentService = Depends(get_document_service),
):
    """Enqueue async analysis job for a document. Returns job_id for status polling."""
    doc = svc.get_document(doc_id)
    if not doc:
        raise NotFoundError("Document not found")
    require_owner_or_admin(doc["user_id"], current_user.user_id, current_user.role)

    # Atomic status transition: only succeed if current status is ready/failed
    # This prevents race conditions where two concurrent requests both pass the check
    updated = svc.try_mark_processing(doc_id)
    if not updated:
        raise ConflictError(
            f"Document is already '{doc['upload_status']}'. Only 'ready' or 'failed' docs can be analyzed."
        )

    from app.tasks.documents import process_upload

    job = process_upload.delay(str(doc_id))
    return JobSubmitResponse(job_id=job.id, doc_id=doc_id)


@router.post("/search", response_model=SemanticSearchResponse)
async def semantic_search(
    body: SemanticSearchRequest,
    current_user: TokenData = Depends(get_current_user),
    chunk_svc: ChunkService = Depends(get_chunk_service),
):
    """Search for chunks semantically similar to a free-text query.

    Encodes the query into an embedding vector and searches the corpus
    using pgvector cosine similarity (HNSW index, no full-table scan).
    """
    # Validate parameters
    if not body.query or len(body.query.strip()) < 3:
        raise ValidationError("Query must be at least 3 characters")
    if body.match_threshold < 0 or body.match_threshold > 1:
        raise ValidationError("match_threshold must be between 0 and 1")
    if body.match_count < 1 or body.match_count > 100:
        raise ValidationError("match_count must be between 1 and 100")

    results = chunk_svc.semantic_search(
        query=body.query,
        source_type=body.source_type,
        match_threshold=body.match_threshold,
        match_count=body.match_count,
    )
    return SemanticSearchResponse(
        query=body.query,
        results=[SemanticSearchResult(**r) for r in results],
        total=len(results),
    )
