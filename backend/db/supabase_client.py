"""
supabase_client.py  ─  Supabase REST API database access
=========================================================
Central database client using PostgREST over HTTPS.
Bypasses the IPv6-only direct connection issue.
"""

import httpx
from typing import Optional

from backend.config import config


class SupabaseDB:
    """Wrapper around Supabase PostgREST API for database operations."""

    def __init__(self):
        self.base_url = f"{config.SUPABASE_URL}/rest/v1"
        self._headers = {
            "apikey": config.SUPABASE_SERVICE_KEY,
            "Authorization": f"Bearer {config.SUPABASE_SERVICE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        self._client = httpx.Client(timeout=30.0)

    # ── Internal request helper ────────────────────────────────────────────
    def _request(self, method: str, table: str, *, params: dict = None,
                 json_data: dict = None) -> list[dict] | dict | None:
        url = f"{self.base_url}/{table}"
        r = self._client.request(
            method, url, headers=self._headers,
            params=params, json=json_data,
        )
        if r.status_code == 204:
            return None
        if r.status_code >= 400:
            raise Exception(f"Supabase REST error {r.status_code}: {r.text[:200]}")
        return r.json()

    # ── Users ──────────────────────────────────────────────────────────────
    def get_user_by_username(self, username: str) -> Optional[dict]:
        result = self._request("GET", "users",
                               params={"username": f"eq.{username}", "limit": "1"})
        if result and isinstance(result, list) and len(result) > 0:
            return result[0]
        return None

    def get_user_by_id(self, user_id: int) -> Optional[dict]:
        result = self._request("GET", "users",
                               params={"id": f"eq.{user_id}", "limit": "1"})
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

    def update_user(self, username: str, updates: dict) -> None:
        self._request("PATCH", "users",
                       params={"username": f"eq.{username}"},
                       json_data=updates)

    def delete_user(self, username: str) -> None:
        self._request("DELETE", "users", params={"username": f"eq.{username}"})

    def list_users(self, role: str = None) -> list[dict]:
        params = {"order": "id.asc"}
        if role:
            params["role"] = f"eq.{role}"
        return self._request("GET", "users", params=params) or []

    def count_users(self) -> int:
        headers = {**self._headers, "Prefer": "count=exact"}
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
        params = {"select": "id,filename,uploaded_by,uploaded_at",
                  "order": "uploaded_at.desc"}
        return self._request("GET", "reference_pdfs", params=params) or []

    def delete_reference_pdf(self, filename: str) -> None:
        self._request("DELETE", "reference_pdfs",
                       params={"filename": f"eq.{filename}"})

    def count_reference_pdfs(self) -> int:
        headers = {**self._headers, "Prefer": "count=exact"}
        r = self._client.get(f"{self.base_url}/reference_pdfs",
                             headers=headers,
                             params={"select": "id", "limit": "0"})
        count = r.headers.get("content-range", "").split("/")[-1]
        return int(count) if count.isdigit() else 0

    # ── Per-user tables (uploads / comparisons) ────────────────────────────
    def insert_upload(self, table: str, filename: str) -> dict:
        return self._request("POST", table, json_data={"filename": filename})

    def delete_upload(self, table: str, filename: str) -> None:
        self._request("DELETE", table, params={"filename": f"eq.{filename}"})

    def list_uploads(self, table: str) -> list[str]:
        rows = self._request("GET", table, params={
            "select": "filename",
            "order": "uploaded_at.desc",
        })
        return [row["filename"] for row in (rows or [])]

    def insert_comparison(self, table: str, data: dict) -> dict:
        return self._request("POST", table, json_data=data)

    def list_comparisons(self, table: str) -> list[dict]:
        return self._request("GET", table, params={
            "select": "id,student_pdf,reference_pdf,result_pdf,similarity,created_at",
            "order": "created_at.desc",
        }) or []

    # ── Health check ────────────────────────────────────────────────────────
    def health_check(self) -> bool:
        try:
            self._request("GET", "users",
                           params={"select": "id", "limit": "1"})
            return True
        except Exception:
            return False


# ── Global singleton ────────────────────────────────────────────────────────
db = SupabaseDB()


def get_db():
    """FastAPI dependency that yields the SupabaseDB instance."""
    yield db
