"""Abstract database interface — repos depend on this, not SupabaseDB."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Database(Protocol):
    """Minimal interface that every repo needs from the DB layer."""

    def select(
        self,
        table: str,
        *,
        filters: dict[str, Any] | None = None,
        columns: str = "*",
    ) -> list[dict[str, Any]]: ...

    def insert(
        self, table: str, *, data: dict[str, Any]
    ) -> dict[str, Any] | list[dict[str, Any]]: ...

    def update(
        self,
        table: str,
        *,
        data: dict[str, Any],
        filters: dict[str, Any],
    ) -> list[dict[str, Any]]: ...

    def delete(
        self, table: str, *, filters: dict[str, Any]
    ) -> list[dict[str, Any]] | None: ...

    def rpc(self, function_name: str, *, params: dict[str, Any]) -> Any: ...

    def execute_ddl(self, sql: str) -> str: ...

    def close(self) -> None: ...
