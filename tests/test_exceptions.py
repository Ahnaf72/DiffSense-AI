"""Tests for domain exceptions and the ownership helper."""

import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import (
    AppError,
    ConflictError,
    NotFoundError,
    NotAuthorizedError,
    ValidationError,
    require_owner_or_admin,
)
from app.models.enums import UserRole


class TestDomainExceptions:
    def test_app_error_base(self):
        err = AppError("test")
        assert err.detail == "test"

    def test_not_found_is_app_error(self):
        assert isinstance(NotFoundError("x"), AppError)

    def test_not_authorized_is_app_error(self):
        assert isinstance(NotAuthorizedError("x"), AppError)

    def test_conflict_is_app_error(self):
        assert isinstance(ConflictError("x"), AppError)

    def test_validation_is_app_error(self):
        assert isinstance(ValidationError("x"), AppError)


class TestRequireOwnerOrAdmin:
    def test_owner_passes(self):
        # Should not raise
        require_owner_or_admin("user-1", "user-1", UserRole.user)

    def test_admin_passes(self):
        # Admin can access any resource
        require_owner_or_admin("user-1", "user-2", UserRole.admin)

    def test_non_owner_non_admin_raises(self):
        with pytest.raises(NotAuthorizedError):
            require_owner_or_admin("user-1", "user-2", UserRole.user)

    def test_uuid_string_comparison(self):
        # UUIDs as strings should match
        require_owner_or_admin("abc-123", "abc-123", UserRole.user)


class TestExceptionHandlers:
    def test_not_found_returns_404(self):
        from app.main import app
        client = TestClient(app, raise_server_exceptions=False)

        # Hit an endpoint that raises NotFoundError
        # We need auth, so just test the handler directly
        from app.core.exceptions import app_error_handler
        import asyncio

        async def _test():
            from fastapi import Request
            # Create a minimal mock request
            class MockRequest:
                method = "GET"
                url = "http://test/test"
            req = MockRequest()
            resp = await app_error_handler(req, NotFoundError("test"))
            assert resp.status_code == 404

            resp = await app_error_handler(req, NotAuthorizedError("test"))
            assert resp.status_code == 403

            resp = await app_error_handler(req, ConflictError("test"))
            assert resp.status_code == 409

            resp = await app_error_handler(req, ValidationError("test"))
            assert resp.status_code == 400

        asyncio.run(_test())
