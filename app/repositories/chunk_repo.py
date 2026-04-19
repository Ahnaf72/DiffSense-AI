from uuid import UUID

from app.db.protocols import Database
from app.repositories.base import BaseRepo


class ChunkRepo(BaseRepo):
    _table = "chunks"

    def get_by_id(self, chunk_id: UUID) -> dict | None:
        return self._get_by(id=chunk_id)

    def list_by_source(self, source_type: str, source_id: UUID) -> list[dict]:
        return self._list_by(source_type=source_type, source_id=source_id)

    def create(self, source_type: str, source_id: UUID, chunk_index: int, content: str, token_count: int = 0, embedding: list[float] | None = None, document_id: UUID | None = None, reference_id: UUID | None = None) -> dict:
        data = {
            "source_type": source_type,
            "source_id": str(source_id),
            "chunk_index": chunk_index,
            "content": content,
            "token_count": token_count,
        }
        if document_id:
            data["document_id"] = str(document_id)
        if reference_id:
            data["reference_id"] = str(reference_id)
        if embedding:
            data["embedding"] = embedding
        return self._insert(data)

    def delete_by_source(self, source_type: str, source_id: UUID) -> None:
        self._delete_by(source_type=source_type, source_id=source_id)
