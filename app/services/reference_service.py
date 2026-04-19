from uuid import UUID

from app.db.protocols import Database
from app.repositories.reference_repo import ReferenceRepo


class ReferenceService:
    def __init__(self, db: Database) -> None:
        self._repo = ReferenceRepo(db)

    def list_active(self) -> list[dict]:
        return self._repo.list_active()

    def list_all(self) -> list[dict]:
        return self._repo.list_all()

    def get(self, ref_id: UUID) -> dict | None:
        return self._repo.get_by_id(ref_id)

    def add(self, title: str, filename: str, file_path: str, uploaded_by: UUID, file_size: int = 0) -> dict:
        return self._repo.create(title, filename, file_path, uploaded_by, file_size)

    def toggle(self, ref_id: UUID, is_active: bool) -> list[dict]:
        return self._repo.toggle_active(ref_id, is_active)

    def remove(self, ref_id: UUID) -> None:
        self._repo.delete(ref_id)
