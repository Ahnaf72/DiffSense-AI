from uuid import UUID

from app.core.security import create_access_token, hash_password, verify_password
from app.db.protocols import Database
from app.repositories.user_repo import UserRepo


class AuthService:
    def __init__(self, db: Database) -> None:
        self._user_repo = UserRepo(db)

    def authenticate(self, username: str, password: str) -> str | None:
        """Return JWT if credentials are valid, else None."""
        user = self._user_repo.get_by_username(username)
        if not user:
            return None
        if not verify_password(password, user["password_hash"]):
            return None
        token = create_access_token({
            "sub": str(user["id"]),
            "username": user["username"],
            "role": user["role"],
        })
        return token

    def register(self, username: str, password: str, full_name: str | None = None) -> dict:
        """Create a new user. Raises if username taken."""
        existing = self._user_repo.get_by_username(username)
        if existing:
            raise ValueError(f"Username '{username}' already exists")
        hashed = hash_password(password)
        return self._user_repo.create(username, hashed, role="user", full_name=full_name)

    def list_users(self) -> list[dict]:
        return self._user_repo.list_all()

    def get_user(self, user_id: UUID) -> dict | None:
        return self._user_repo.get_by_id(user_id)
