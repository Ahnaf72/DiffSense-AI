"""Database session module — re-exports SupabaseDB for backward compatibility."""

from app.db.supabase_client import SupabaseDB, get_db  # noqa: F401

__all__ = ["SupabaseDB", "get_db"]
