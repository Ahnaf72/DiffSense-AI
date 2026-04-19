from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.core.deps import get_auth_service, get_current_user, require_admin
from app.core.exceptions import NotFoundError, NotAuthorizedError
from app.schemas.user import TokenData, UserResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserResponse])
async def list_users(
    _admin: TokenData = Depends(require_admin),
    svc: AuthService = Depends(get_auth_service),
):
    return svc.list_users()


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    current_user: TokenData = Depends(get_current_user),
    svc: AuthService = Depends(get_auth_service),
):
    from app.core.exceptions import require_owner_or_admin
    require_owner_or_admin(str(user_id), current_user.user_id, current_user.role)
    user = svc.get_user(user_id)
    if not user:
        raise NotFoundError("User not found")
    return user
