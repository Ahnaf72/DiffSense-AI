from collections.abc import Callable
from uuid import UUID

from fastapi import Depends, HTTPException, status  # HTTPException/status still needed for 401 auth responses
from fastapi.security import OAuth2PasswordBearer

from app.core.exceptions import NotAuthorizedError
from app.core.security import decode_access_token
from app.db.supabase_client import SupabaseDB, get_db
from app.models.enums import UserRole
from app.schemas.user import TokenData
from app.services.auth_service import AuthService
from app.services.chunk_service import ChunkService
from app.services.document_service import DocumentService
from app.services.reference_service import ReferenceService
from app.services.report_service import ReportService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


# ── Auth dependencies ──────────────────────────────────────────────

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: SupabaseDB = Depends(get_db),
) -> TokenData:
    """Decode JWT and validate that the user still exists in DB."""
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        user_id = payload.get("sub")
        username = payload.get("username")
        role = payload.get("role")
        if not user_id or not username or not role:
            raise ValueError
        token_data = TokenData(user_id=UUID(user_id), username=username, role=role)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    # Verify user still exists in DB (revocation check)
    repo = AuthService(db)._user_repo
    user = repo.get_by_id(token_data.user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token_data


async def require_admin(
    current_user: TokenData = Depends(get_current_user),
) -> TokenData:
    """Shorthand: require admin role."""
    if current_user.role != UserRole.admin:
        raise NotAuthorizedError("Admin access required")
    return current_user


def require_role(*roles: UserRole) -> Callable:
    """Factory: create a dependency that requires one of the given roles."""
    async def _check_role(
        current_user: TokenData = Depends(get_current_user),
    ) -> TokenData:
        if current_user.role not in roles:
            allowed = ", ".join(r.value for r in roles)
            raise NotAuthorizedError(f"Role '{current_user.role}' not allowed. Required: {allowed}")
        return current_user
    return _check_role


# ── Service dependencies (one instance per request) ────────────────

def get_auth_service(db: SupabaseDB = Depends(get_db)) -> AuthService:
    return AuthService(db)


def get_document_service(db: SupabaseDB = Depends(get_db)) -> DocumentService:
    return DocumentService(db)


def get_reference_service(db: SupabaseDB = Depends(get_db)) -> ReferenceService:
    return ReferenceService(db)


def get_report_service(db: SupabaseDB = Depends(get_db)) -> ReportService:
    return ReportService(db)


def get_chunk_service(db: SupabaseDB = Depends(get_db)) -> ChunkService:
    return ChunkService(db)


# ── Model dependencies (singleton) ─────────────────────────────────

def get_embedding_model():
    """FastAPI dependency that returns the singleton embedding model."""
    from app.core.embedding import get_embedding_model as _load
    return _load()
