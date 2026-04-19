"""Local file storage — saves uploads to disk, simulates Supabase Storage."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from uuid import UUID

from app.core.config import settings

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".pdf"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


def _upload_root() -> Path:
    return Path(settings.upload_dir)


def ensure_upload_dir() -> None:
    """Create upload directory tree if it doesn't exist."""
    root = _upload_root()
    root.mkdir(parents=True, exist_ok=True)


def validate_extension(filename: str) -> str:
    """Raise ValueError if the file extension is not allowed."""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise ValueError(f"File type '{ext}' not allowed. Allowed: {allowed}")
    return ext


def user_upload_dir(user_id: UUID) -> Path:
    """Return (and create) the per-user upload directory."""
    d = _upload_root() / str(user_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_upload(
    user_id: UUID,
    doc_id: UUID,
    filename: str,
    src_path: Path,
) -> str:
    """Move/copy the uploaded file into the user's directory.

    Returns the relative path (from upload_root) used as ``file_path`` in DB.
    """
    dest_dir = user_upload_dir(user_id)
    # Use doc_id as prefix to avoid name collisions
    safe_name = f"{doc_id}_{filename}"
    dest = dest_dir / safe_name
    shutil.move(str(src_path), str(dest))
    rel_path = f"{user_id}/{safe_name}"
    logger.info("Saved upload %s -> %s", filename, rel_path)
    return rel_path


def delete_file(file_path: str) -> None:
    """Remove a previously uploaded file."""
    full = _upload_root() / file_path
    if full.exists():
        full.unlink()
        logger.info("Deleted file %s", file_path)
