from uuid import UUID

from app.db.protocols import Database
from app.repositories.base import BaseRepo


class ReferenceRepo(BaseRepo):
    _table = "reference_corpus"

    def get_by_id(self, ref_id: UUID) -> dict | None:
        return self._get_by(id=ref_id)

    def list_active(self) -> list[dict]:
        return self._db.select(self._table, filters={"is_active": "eq.true"})

    def list_all(self) -> list[dict]:
        return self._list_all()

    def create(self, title: str, filename: str, file_path: str, uploaded_by: UUID, file_size: int = 0) -> dict:
        return self._insert({
            "title": title,
            "filename": filename,
            "file_path": file_path,
            "file_size": file_size,
            "uploaded_by": str(uploaded_by),
        })

    def toggle_active(self, ref_id: UUID, is_active: bool) -> list[dict]:
        return self._update_by({"is_active": is_active}, id=ref_id)

    def delete(self, ref_id: UUID) -> None:
        self._delete_by(id=ref_id)
