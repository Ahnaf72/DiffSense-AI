import tempfile
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, UploadFile, status

from app.core.deps import get_current_user, get_reference_service, get_chunk_service, require_admin
from app.core.exceptions import AppError, NotFoundError, ValidationError
from app.core.storage import MAX_FILE_SIZE, ensure_upload_dir, validate_extension
from app.schemas.reference import ReferenceCreate, ReferenceResponse
from app.schemas.user import TokenData
from app.services.reference_service import ReferenceService
from app.services.chunk_service import ChunkService

router = APIRouter(prefix="/references", tags=["references"])


@router.get("", response_model=list[ReferenceResponse])
async def list_references(
    active_only: bool = True,
    _user: TokenData = Depends(get_current_user),
    svc: ReferenceService = Depends(get_reference_service),
):
    return svc.list_active() if active_only else svc.list_all()


@router.post("", response_model=ReferenceResponse, status_code=status.HTTP_201_CREATED)
async def add_reference(
    body: ReferenceCreate,
    admin: TokenData = Depends(require_admin),
    svc: ReferenceService = Depends(get_reference_service),
):
    return svc.add(body.title, body.filename, body.file_path, admin.user_id, body.file_size)


@router.patch("/{ref_id}/toggle", response_model=ReferenceResponse)
async def toggle_reference(
    ref_id: UUID,
    is_active: bool = True,
    _admin: TokenData = Depends(require_admin),
    svc: ReferenceService = Depends(get_reference_service),
):
    ref = svc.get(ref_id)
    if not ref:
        raise NotFoundError("Reference not found")
    svc.toggle(ref_id, is_active)
    return svc.get(ref_id)


@router.delete("/{ref_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_reference(
    ref_id: UUID,
    _admin: TokenData = Depends(require_admin),
    svc: ReferenceService = Depends(get_reference_service),
):
    ref = svc.get(ref_id)
    if not ref:
        raise NotFoundError("Reference not found")
    svc.remove(ref_id)


@router.post("/upload", response_model=ReferenceResponse, status_code=status.HTTP_201_CREATED)
async def upload_reference_pdf(
    title: str,
    file: UploadFile,
    admin: TokenData = Depends(require_admin),
    svc: ReferenceService = Depends(get_reference_service),
):
    """Upload a reference PDF to the corpus (admin only)."""
    if not file.filename:
        raise ValidationError("Filename is required")
    try:
        validate_extension(file.filename)
    except ValueError as e:
        raise ValidationError(str(e))

    ensure_upload_dir()
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            file_size = 0
            while chunk := await file.read(1024 * 1024):
                file_size += len(chunk)
                if file_size > MAX_FILE_SIZE:
                    raise ValidationError(f"File too large. Max {MAX_FILE_SIZE // (1024*1024)} MB")
                tmp.write(chunk)
            tmp_path = Path(tmp.name)

        # Save to uploads directory with reference prefix
        from app.core.config import settings
        ref_filename = f"ref_{file.filename}"
        dest_path = Path(settings.upload_dir) / ref_filename
        import shutil
        shutil.move(str(tmp_path), str(dest_path))

        ref = svc.add(
            title=title,
            filename=file.filename,
            file_path=str(dest_path.relative_to(settings.upload_dir)),
            uploaded_by=admin.user_id,
            file_size=file_size,
        )
        return ref
    except Exception:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise


@router.post("/{ref_id}/embed")
async def precompute_embeddings(
    ref_id: UUID,
    _admin: TokenData = Depends(require_admin),
    svc: ReferenceService = Depends(get_reference_service),
    chunk_svc: ChunkService = Depends(get_chunk_service),
):
    """Precompute embeddings for a reference document (admin only)."""
    ref = svc.get(ref_id)
    if not ref:
        raise NotFoundError("Reference not found")

    from app.core.config import settings
    file_path = Path(settings.upload_dir) / ref["file_path"]

    if not file_path.exists():
        raise NotFoundError(f"Reference file not found: {file_path}")

    # Extract text
    from app.core.pdf import extract_pdf
    extraction = extract_pdf(file_path, extract_images=False)

    # Chunk
    from app.core.chunker import chunk_text
    chunks = chunk_text(extraction.text, strategy="paragraph", max_tokens=256)

    # Generate embeddings
    from app.core.embedding import encode_texts
    vectors = encode_texts([c.content for c in chunks], batch_size=64)

    # Store chunks with embeddings
    chunk_dicts = [
        {
            "chunk_index": c.chunk_index,
            "content": c.content,
            "token_count": c.token_count,
        }
        for c in chunks
    ]

    try:
        stored = chunk_svc.store_chunks_with_embeddings(
            source_type="reference",
            source_id=ref_id,
            chunks=chunk_dicts,
            embeddings=vectors,
        )
    except Exception as exc:
        raise AppError(f"Failed to store chunks and embeddings: {str(exc)}")

    return {
        "status": "ok",
        "ref_id": str(ref_id),
        "chunks_stored": len(stored),
        "embeddings_generated": len(vectors),
    }
