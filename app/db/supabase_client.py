from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


# ── Shared httpx client (connection pool reuse) ──────────────────────

_shared_client: httpx.Client | None = None


def _get_shared_client() -> httpx.Client:
    """Lazily create a shared httpx.Client for connection pooling."""
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.Client(
            base_url=f"{settings.supabase_url}/rest/v1",
            headers={
                "apikey": settings.supabase_service_key,
                "Authorization": f"Bearer {settings.supabase_service_key}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
            timeout=30.0,
        )
    return _shared_client


class SupabaseDB:
    """Database client that uses Supabase PostgREST (DML) and CLI (DDL).

    Why not SQLAlchemy directly?
    The Supabase hostname (db.*.supabase.co) resolves to IPv6 only,
    which Python's socket layer cannot connect to on this Windows machine.
    Workaround: all DML goes through the PostgREST HTTPS API, and DDL
    (CREATE / DROP TABLE) is executed via ``supabase db query``.
    """

    def __init__(self) -> None:
        self._base_url: str = settings.supabase_url
        self._rest_url: str = f"{self._base_url}/rest/v1"
        self._rpc_url: str = f"{self._base_url}/rest/v1/rpc"
        self._service_key: str = settings.supabase_service_key
        self._anon_key: str = settings.supabase_anon_key
        self._client: httpx.Client = _get_shared_client()

    # ── DML via PostgREST ──────────────────────────────────────────

    def _rest_request(
        self,
        method: str,
        table: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]] | dict[str, Any] | None:
        """Low-level REST helper. Returns parsed JSON or None."""
        url = f"/{table}"
        response = self._client.request(
            method, url, params=params, json=json_body
        )
        response.raise_for_status()
        if response.status_code == 204:
            return None
        return response.json()

    def select(
        self,
        table: str,
        *,
        filters: dict[str, Any] | None = None,
        columns: str = "*",
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"select": columns}
        if filters:
            params.update(filters)
        result = self._rest_request("GET", table, params=params)
        return result if isinstance(result, list) else [result]

    def insert(
        self, table: str, *, data: dict[str, Any]
    ) -> dict[str, Any] | list[dict[str, Any]]:
        return self._rest_request("POST", table, json_body=data)

    def update(
        self,
        table: str,
        *,
        data: dict[str, Any],
        filters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        return self._rest_request("PATCH", table, params=filters, json_body=data)

    def delete(
        self, table: str, *, filters: dict[str, Any]
    ) -> list[dict[str, Any]] | None:
        return self._rest_request("DELETE", table, params=filters)

    # ── RPC (Supabase functions — needed for pgvector) ────────────────

    def rpc(self, function_name: str, *, params: dict[str, Any]) -> Any:
        """Call a Supabase RPC function (POST /rpc/{function_name}).

        Used for operations that PostgREST can't handle natively,
        such as storing/querying pgvector embeddings.
        """
        response = self._client.post(
            f"/rpc/{function_name}",
            json=params,
        )
        response.raise_for_status()
        if response.status_code == 204:
            return None
        return response.json()

    # ── DDL via Supabase CLI ───────────────────────────────────────

    def _cli_query(self, sql: str) -> str:
        """Run a SQL statement through ``supabase db query``."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".sql", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(sql)
            tmp_path = tmp.name

        try:
            import subprocess

            result = subprocess.run(
                [
                    str(Path(settings.supabase_cli_path)),
                    "db",
                    "query",
                    "-f",
                    tmp_path,
                    "--linked",
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                logger.error("Supabase CLI error: %s", result.stderr)
                raise RuntimeError(f"Supabase CLI error: {result.stderr}")
            return result.stdout
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def execute_ddl(self, sql: str) -> str:
        """Public wrapper for DDL statements (CREATE/DROP/ALTER)."""
        return self._cli_query(sql)

    # ── Lifecycle ──────────────────────────────────────────────────

    def close(self) -> None:
        """No-op: shared client is reused across requests."""
        pass

    @classmethod
    def shutdown_pool(cls) -> None:
        """Shut down the shared httpx connection pool (app shutdown only)."""
        global _shared_client
        if _shared_client is not None:
            _shared_client.close()
            _shared_client = None

    def __enter__(self) -> SupabaseDB:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


# ── FastAPI dependency ──────────────────────────────────────────────

def get_db() -> SupabaseDB:
    """Yield a SupabaseDB instance (FastAPI Depends-friendly)."""
    db = SupabaseDB()
    try:
        yield db
    finally:
        db.close()


# ── Celery task helper ──────────────────────────────────────────────

from contextlib import contextmanager

@contextmanager
def task_db():
    """Context manager that yields a SupabaseDB for use in Celery tasks.

    Usage:
        with task_db() as db:
            svc = DocumentService(db)
            ...
    """
    db = SupabaseDB()
    try:
        yield db
    finally:
        db.close()
