from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.deps import get_auth_service, get_current_user
from app.core.exceptions import ConflictError
from app.schemas.user import LoginRequest, TokenResponse, TokenData, UserCreate, UserResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(request: Request, body: LoginRequest, svc: AuthService = Depends(get_auth_service)):
    # Rate limiting: 5 attempts per minute per IP
    from app.main import app as _app
    _app.state.limiter.limit("5/minute")(request)
    token = svc.authenticate(body.username, body.password)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return TokenResponse(access_token=token)


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(body: UserCreate, svc: AuthService = Depends(get_auth_service)):
    try:
        user = svc.register(body.username, body.password, body.full_name)
    except ValueError as e:
        raise ConflictError(str(e))
    return user


@router.get("/me", response_model=TokenData)
async def read_me(current_user: TokenData = Depends(get_current_user)):
    return current_user
