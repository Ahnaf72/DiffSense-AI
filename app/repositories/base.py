"""Base repository — shared CRUD helpers for all repos."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.db.protocols import Database


class BaseRepo:
    """Common PostgREST filter builders and CRUD operations.

    Subclasses set ``_table`` and inherit ready-made helpers.
    """

    _table: str

    def __init__(self, db: Database) -> None:
        self._db = db

    # ── Filter helpers ────────────────────────────────────────────

    @staticmethod
    def _eq(field: str, value: Any) -> dict[str, str]:
        return {field: f"eq.{value}"}

    # ── Generic CRUD ──────────────────────────────────────────────

    def _get_by(self, **filters: Any) -> dict | None:
        rows = self._db.select(self._table, filters=self._eq_bulk(**filters))
        return rows[0] if rows else None

    def _eq_bulk(self, **filters: Any) -> dict[str, str]:
        return {k: f"eq.{v}" for k, v in filters.items()}

    def _list_by(self, **filters: Any) -> list[dict]:
        return self._db.select(self._table, filters=self._eq_bulk(**filters))

    def _list_paginated(self, limit: int = 50, offset: int = 0, **filters: Any) -> list[dict]:
        """Paginated select with limit/offset via PostgREST query params."""
        # Enforce safety limits
        if limit < 1 or limit > 100:
            limit = min(max(limit, 1), 100)
        if offset < 0:
            offset = 0
        params = self._eq_bulk(**filters)
        params["limit"] = str(limit)
        params["offset"] = str(offset)
        params["order"] = "created_at.desc"
        return self._db.select(self._table, filters=params)

    def _list_all(self) -> list[dict]:
        # Enforce safety limit to prevent excessive data retrieval
        return self._db.select(self._table, filters={"limit": "100"})

    def _insert(self, data: dict[str, Any]) -> dict:
        result = self._db.insert(self._table, data=data)
        # Supabase PostgREST returns a list with Prefer: return=representation
        if isinstance(result, list) and result:
            return result[0]
        if isinstance(result, dict):
            return result
        return {}

    def _update_by(self, data: dict[str, Any], **filters: Any) -> list[dict]:
        return self._db.update(self._table, data=data, filters=self._eq_bulk(**filters))

    def _delete_by(self, **filters: Any) -> None:
        self._db.delete(self._table, filters=self._eq_bulk(**filters))
