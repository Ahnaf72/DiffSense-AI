from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from httpx import HTTPStatusError
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.v1.router import router as v1_router
from app.core.config import settings
from app.core.exceptions import (
    AppError,
    app_error_handler,
    httpx_error_handler,
    unhandled_exception_handler,
)
from app.core.logging import setup_logging, set_request_id


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fail fast if critical config is missing
    if not settings.secret_key:
        raise RuntimeError("SECRET_KEY must be set in .env — refusing to start with empty key")
    if not settings.supabase_url or not settings.supabase_service_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env")

    setup_logging()

    # Validate Redis connection (Celery broker)
    try:
        import redis
        r = redis.from_url(settings.redis_url, socket_connect_timeout=5)
        r.ping()
        r.close()
    except Exception as e:
        raise RuntimeError(f"Redis connection failed: {e}")

    yield
    from app.db.supabase_client import SupabaseDB
    SupabaseDB.shutdown_pool()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan,
)


# ── Request ID middleware ────────────────────────────────────────────

class RequestIdMiddleware(BaseHTTPMiddleware):
    """Assign a unique ID to every request and propagate to logs."""

    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-ID", str(uuid4()))
        set_request_id(rid)
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response


app.add_middleware(RequestIdMiddleware)

# ── Rate limiting ────────────────────────────────────────────────────

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi.responses import JSONResponse

_limiter = Limiter(key_func=get_remote_address, default_limits=[])
app.state.limiter = _limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})


# ── CORS ────────────────────────────────────────────────────────────

if settings.cors_origin_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(v1_router)
app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(HTTPStatusError, httpx_error_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)
