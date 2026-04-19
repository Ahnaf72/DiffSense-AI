from uuid import UUID

from app.db.protocols import Database
from app.repositories.base import BaseRepo


class ReportRepo(BaseRepo):
    _table = "reports"

    def get_by_id(self, report_id: UUID) -> dict | None:
        return self._get_by(id=report_id)

    def list_by_user(self, user_id: UUID) -> list[dict]:
        return self._list_by(user_id=user_id)

    def list_by_document(self, document_id: UUID) -> list[dict]:
        return self._list_by(document_id=document_id)

    def create(self, user_id: UUID, document_id: UUID) -> dict:
        return self._insert({
            "user_id": str(user_id),
            "document_id": str(document_id),
        })

    def update(self, report_id: UUID, **fields) -> list[dict]:
        return self._update_by(fields, id=report_id)

    def delete(self, report_id: UUID) -> None:
        self._delete_by(id=report_id)


class MatchRepo(BaseRepo):
    _table = "matches"

    def list_by_report(self, report_id: UUID) -> list[dict]:
        return self._list_by(report_id=report_id)

    def create(self, upload_chunk_id: UUID, reference_chunk_id: UUID, similarity_score: float, report_id: UUID | None = None) -> dict:
        data = {
            "upload_chunk_id": str(upload_chunk_id),
            "reference_chunk_id": str(reference_chunk_id),
            "similarity_score": similarity_score,
        }
        if report_id:
            data["report_id"] = str(report_id)
        return self._insert(data)

    def delete_by_report(self, report_id: UUID) -> None:
        self._delete_by(report_id=report_id)
