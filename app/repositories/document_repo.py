from uuid import UUID

from app.db.protocols import Database
from app.repositories.base import BaseRepo


class DocumentRepo(BaseRepo):
    _table = "documents"

    def get_by_id(self, doc_id: UUID) -> dict | None:
        return self._get_by(id=doc_id)

    def list_by_user(self, user_id: UUID) -> list[dict]:
        return self._list_by(user_id=user_id)

    def list_by_user_paginated(self, user_id: UUID, limit: int = 50, offset: int = 0) -> list[dict]:
        return self._list_paginated(limit=limit, offset=offset, user_id=user_id)

    def count_by_user(self, user_id: UUID) -> int:
        """Count total documents for a user (for pagination)."""
        # Use HEAD request with Prefer: count=exact for efficient counting
        result = self._db.select(
            self._table,
            filters={"user_id": f"eq.{user_id}"},
            columns="*",
        )
        # For now, use the length of results (PostgREST count header would be better)
        return len(result)

    def create(self, user_id: UUID, filename: str, file_path: str, file_size: int = 0, mime_type: str = "application/pdf") -> dict:
        return self._insert({
            "user_id": str(user_id),
            "filename": filename,
            "file_path": file_path,
            "file_size": file_size,
            "mime_type": mime_type,
        })

    def update_status(self, doc_id: UUID, status: str) -> list[dict]:
        return self._update_by({"upload_status": status}, id=doc_id)

    def try_update_status(self, doc_id: UUID, new_status: str, from_statuses: tuple[str, ...]) -> bool:
        """Atomic conditional update — only transitions if current status is in from_statuses.

        Uses PostgREST's filter-on-PATCH to ensure the update only applies
        when the current status matches, preventing TOCTOU race conditions.
        Returns True if the row was updated, False otherwise.
        """
        filters = {"id": f"eq.{doc_id}"}
        # Add OR filter for allowed source statuses: upload_status=in.(ready,failed)
        filters["upload_status"] = f"in.({','.join(from_statuses)})"
        result = self._db.update(self._table, data={"upload_status": new_status}, filters=filters)
        return bool(result)

    def update_file_path(self, doc_id: UUID, file_path: str) -> list[dict]:
        return self._update_by({"file_path": file_path}, id=doc_id)

    def delete(self, doc_id: UUID) -> None:
        self._delete_by(id=doc_id)
