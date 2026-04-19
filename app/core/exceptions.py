"""Centralized exception handlers for the FastAPI app."""

import logging

from fastapi import Request
from fastapi.responses import JSONResponse

from app.models.enums import UserRole

logger = logging.getLogger(__name__)


# ── Domain exceptions ────────────────────────────────────────────────


class AppError(Exception):
    """Base for all application-level errors."""
    def __init__(self, detail: str = "Error") -> None:
        self.detail = detail
        super().__init__(detail)


class NotFoundError(AppError):
    """Resource not found (404)."""


class NotAuthorizedError(AppError):
    """User lacks permission (403)."""


class ConflictError(AppError):
    """State conflict (409)."""


class ValidationError(AppError):
    """Input validation failure (400)."""


# ── Ownership helper ─────────────────────────────────────────────────

def require_owner_or_admin(resource_user_id: str, current_user_id, current_role) -> None:
    """Raise NotAuthorizedError if the user is neither the owner nor an admin."""
    if str(resource_user_id) != str(current_user_id) and current_role != UserRole.admin:
        raise NotAuthorizedError("Not authorized")


# ── FastAPI exception handlers ────────────────────────────────────────


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Map domain exceptions to HTTP responses (isinstance-based for subclass support)."""
    if isinstance(exc, NotFoundError):
        code = 404
    elif isinstance(exc, NotAuthorizedError):
        code = 403
    elif isinstance(exc, ConflictError):
        code = 409
    elif isinstance(exc, ValidationError):
        code = 400
    else:
        code = 400
    return JSONResponse(status_code=code, content={"detail": exc.detail})


async def httpx_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch httpx HTTPStatusError (Supabase REST failures)."""
    from httpx import HTTPStatusError

    if isinstance(exc, HTTPStatusError):
        logger.error("Supabase REST error %s %s: %s", request.method, request.url, exc)
        return JSONResponse(
            status_code=502,
            content={"detail": "Database service error", "path": str(request.url)},
        )
    raise exc


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unexpected errors."""
    logger.exception("Unhandled exception on %s %s", request.method, request.url)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )
