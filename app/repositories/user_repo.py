from uuid import UUID

from app.db.protocols import Database
from app.repositories.base import BaseRepo


class UserRepo(BaseRepo):
    _table = "users"

    def get_by_username(self, username: str) -> dict | None:
        return self._get_by(username=username)

    def get_by_id(self, user_id: UUID) -> dict | None:
        return self._get_by(id=user_id)

    def create(self, username: str, password_hash: str, role: str = "user", full_name: str | None = None) -> dict:
        data: dict = {"username": username, "password_hash": password_hash, "role": role}
        if full_name:
            data["full_name"] = full_name
        return self._insert(data)

    def update(self, user_id: UUID, **fields) -> list[dict]:
        return self._update_by(fields, id=user_id)

    def delete(self, user_id: UUID) -> None:
        self._delete_by(id=user_id)

    def list_all(self) -> list[dict]:
        return self._list_all()
