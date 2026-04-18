from backend.admin_db import db as supabase_db

def get_db():
    """Return the SupabaseDB instance (legacy helper)."""
    return supabase_db