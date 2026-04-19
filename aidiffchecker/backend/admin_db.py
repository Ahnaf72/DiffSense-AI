"""
admin_db.py  ─  Supabase REST API database access
===================================================
Uses the Supabase PostgREST API over HTTPS instead of
direct psycopg2 connection (which fails on IPv6-only hosts).
"""

import os
import httpx
from typing import Optional

from backend.config import config

# Supabase REST API configuration
SUPABASE_URL = config.SUPABASE_URL
SUPABASE_SERVICE_KEY = config.SUPABASE_SERVICE_KEY


class SupabaseDB:
    """Wrapper around Supabase PostgREST API for database operations."""

    def __init__(self):
        self.base_url = f"{SUPABASE_URL}/rest/v1"
        self.headers = {
            "apikey": SUPABASE_SERVICE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        self._client = httpx.Client(timeout=30.0)

    def _request(self, method: str, table: str, *, params: dict = None,
                 json_data: dict = None) -> list[dict] | dict | None:
        url = f"{self.base_url}/{table}"
        r = self._client.request(
            method, url, headers=self.headers,
            params=params, json=json_data,
        )
        if r.status_code == 204:
            return None
        r.raise_for_status()
        return r.json()

    # ── Users ──────────────────────────────────────────────────────────────
    def get_user_by_username(self, username: str) -> Optional[dict]:
        result = self._request("GET", "users",
                               params={"username": f"eq.{username}", "limit": "1"})
        if result and isinstance(result, list) and len(result) > 0:
            return result[0]
        return None

    def insert_user(self, username: str, full_name: str,
                    hashed_password: str, role: str) -> dict:
        return self._request("POST", "users", json_data={
            "username": username,
            "full_name": full_name,
            "hashed_password": hashed_password,
            "role": role,
        })

    def delete_user(self, username: str) -> None:
        self._request("DELETE", "users", params={"username": f"eq.{username}"})

    def list_users(self, role: str = None) -> list[dict]:
        params = {}
        if role:
            params["role"] = f"eq.{role}"
        return self._request("GET", "users", params=params) or []

    def count_users(self) -> int:
        headers = {**self.headers, "Prefer": "count=exact"}
        r = self._client.get(f"{self.base_url}/users",
                             headers=headers,
                             params={"select": "id", "limit": "0"})
        count = r.headers.get("content-range", "").split("/")[-1]
        return int(count) if count.isdigit() else 0

    # ── Reference PDFs ─────────────────────────────────────────────────────
    def insert_reference_pdf(self, filename: str, uploaded_by: int) -> dict:
        return self._request("POST", "reference_pdfs", json_data={
            "filename": filename,
            "uploaded_by": uploaded_by,
        })

    def list_reference_pdfs(self) -> list[dict]:
        params = {"select": "filename,uploaded_by,uploaded_at",
                  "order": "uploaded_at.desc"}
        return self._request("GET", "reference_pdfs", params=params) or []

    def delete_reference_pdf(self, filename: str) -> None:
        self._request("DELETE", "reference_pdfs",
                       params={"filename": f"eq.{filename}"})

    def count_reference_pdfs(self) -> int:
        headers = {**self.headers, "Prefer": "count=exact"}
        r = self._client.get(f"{self.base_url}/reference_pdfs",
                             headers=headers,
                             params={"select": "id", "limit": "0"})
        count = r.headers.get("content-range", "").split("/")[-1]
        return int(count) if count.isdigit() else 0

    # ── Health check ────────────────────────────────────────────────────────
    def health_check(self) -> bool:
        try:
            self._request("GET", "users",
                           params={"select": "id", "limit": "1"})
            return True
        except Exception:
            return False


# Global singleton
db = SupabaseDB()


# ── FastAPI dependency (kept for compatibility) ────────────────────────────
# The original code used SQLAlchemy Session injection. We keep the
# dependency interface but return our SupabaseDB instance instead.
class _DBSession:
    """Compatibility shim: provides SQLAlchemy-like Session interface
    that delegates to SupabaseDB REST calls."""

    def __init__(self):
        self._db = db

    def execute(self, stmt, params=None):
        """Handle raw SQL-style queries by translating to REST calls.
        This is a compatibility layer — new code should use db directly."""
        # This is intentionally minimal — only covers queries used in main.py
        raise NotImplementedError(
            "Direct SQL execution not supported with Supabase REST API. "
            "Use db.get_user_by_username(), db.insert_user(), etc. instead."
        )

    def query(self, model):
        """SQLAlchemy ORM compatibility — not fully supported."""
        raise NotImplementedError(
            "ORM queries not supported with Supabase REST API. "
            "Use db methods directly."
        )

    def close(self):
        pass

    def commit(self):
        pass


def get_admin_db():
    """FastAPI dependency that yields the SupabaseDB instance."""
    yield db


# -----------------------------
# REGISTER NEW USER
# -----------------------------
def register_user(username: str, role: str):
    db.insert_user(username, role, "", role)
    print(f"[INFO] Added {username} to admin DB")

    # Create per-user tables in the same database
    create_user_db(username, role)
