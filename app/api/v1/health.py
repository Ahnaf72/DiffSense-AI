from fastapi import APIRouter, Depends

from app.db.supabase_client import SupabaseDB, get_db

router = APIRouter()


@router.get("/health", tags=["health"])
async def health_check():
    """Liveness probe — no DB dependency."""
    return {"status": "ok", "service": "DiffSense-AI"}


@router.get("/health/db", tags=["health"])
async def db_health_check(db: SupabaseDB = Depends(get_db)):
    """Readiness probe — verifies Supabase REST connectivity."""
    try:
        db._client.get("/")
        db_status = "ok"
    except Exception as exc:
        db_status = f"error: {exc}"
    return {"status": "ok" if db_status == "ok" else "degraded", "db": db_status}
