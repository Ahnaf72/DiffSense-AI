from pathlib import Path
from uuid import UUID

from app.core.storage import delete_file, save_upload, validate_extension
from app.db.protocols import Database
from app.repositories.document_repo import DocumentRepo


class DocumentService:
    def __init__(self, db: Database) -> None:
        self._repo = DocumentRepo(db)

    def list_user_documents(self, user_id: UUID) -> list[dict]:
        return self._repo.list_by_user(user_id)

    def list_user_documents_paginated(self, user_id: UUID, limit: int = 50, offset: int = 0) -> list[dict]:
        return self._repo.list_by_user_paginated(user_id, limit=limit, offset=offset)

    def count_user_documents(self, user_id: UUID) -> int:
        return self._repo.count_by_user(user_id)

    def get_document(self, doc_id: UUID) -> dict | None:
        return self._repo.get_by_id(doc_id)

    def upload_document(self, user_id: UUID, filename: str, file_path: str, file_size: int = 0, mime_type: str = "application/pdf") -> dict:
        return self._repo.create(user_id, filename, file_path, file_size, mime_type)

    def upload_file(self, user_id: UUID, filename: str, src_path: Path, file_size: int) -> dict:
        """Validate, save file to disk, and create DB metadata record."""
        validate_extension(filename)
        # Create a preliminary DB record to get a doc_id
        doc = self._repo.create(user_id, filename, "", file_size, "application/pdf")
        doc_id = UUID(doc["id"])
        # Save file to disk
        rel_path = save_upload(user_id, doc_id, filename, src_path)
        # Update DB with real path and mark ready
        self._repo.update_file_path(doc_id, rel_path)
        self._repo.update_status(doc_id, "ready")
        # Re-fetch to get updated record
        return self._repo.get_by_id(doc_id) or doc

    def mark_ready(self, doc_id: UUID) -> list[dict]:
        return self._repo.update_status(doc_id, "ready")

    def mark_processing(self, doc_id: UUID) -> list[dict]:
        return self._repo.update_status(doc_id, "processing")

    def try_mark_processing(self, doc_id: UUID) -> bool:
        """Atomically transition from ready/failed → processing.

        Returns True if the transition succeeded, False if the document
        was already in a different state (race condition protection).
        """
        return self._repo.try_update_status(doc_id, "processing", from_statuses=("ready", "failed"))

    def mark_failed(self, doc_id: UUID) -> list[dict]:
        return self._repo.update_status(doc_id, "failed")

    def delete_document(self, doc_id: UUID) -> None:
        doc = self._repo.get_by_id(doc_id)
        if doc and doc.get("file_path"):
            delete_file(doc["file_path"])
        self._repo.delete(doc_id)
