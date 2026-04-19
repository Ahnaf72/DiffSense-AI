from uuid import UUID

from app.db.protocols import Database
from app.repositories.report_repo import MatchRepo, ReportRepo


class ReportService:
    def __init__(self, db: Database) -> None:
        self._report_repo = ReportRepo(db)
        self._match_repo = MatchRepo(db)

    def get_report(self, report_id: UUID) -> dict | None:
        return self._report_repo.get_by_id(report_id)

    def list_user_reports(self, user_id: UUID) -> list[dict]:
        return self._report_repo.list_by_user(user_id)

    def list_document_reports(self, document_id: UUID) -> list[dict]:
        return self._report_repo.list_by_document(document_id)

    def create_report(self, user_id: UUID, document_id: UUID) -> dict:
        return self._report_repo.create(user_id, document_id)

    def update_report(self, report_id: UUID, status: str | None = None, overall_score: float | None = None, total_matches: int | None = None, score_breakdown: dict | None = None, error_message: str | None = None) -> list[dict]:
        """Update report fields including optional score_breakdown (jsonb)."""
        return self._report_repo.update(report_id, status=status, overall_score=overall_score, total_matches=total_matches, score_breakdown=score_breakdown, error_message=error_message)

    def get_matches(self, report_id: UUID) -> list[dict]:
        return self._match_repo.list_by_report(report_id)

    def add_match(self, upload_chunk_id: UUID, reference_chunk_id: UUID, similarity_score: float, report_id: UUID | None = None) -> dict:
        return self._match_repo.create(upload_chunk_id, reference_chunk_id, similarity_score, report_id)

    def delete_report(self, report_id: UUID) -> None:
        self._match_repo.delete_by_report(report_id)
        self._report_repo.delete(report_id)
