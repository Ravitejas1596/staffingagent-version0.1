"""Unit tests for tenant session UUID guard.

Full cross-tenant RLS enforcement is verified against a real PostgreSQL
in tests/security/test_rls_integration.py (skipped when DATABASE_URL is
not set).
"""
from __future__ import annotations

import uuid

import pytest

from app_platform.api.database import _coerce_tenant_uuid


class TestCoerceTenantUuid:
    def test_accepts_valid_uuid_string(self) -> None:
        tid = "11111111-1111-1111-1111-111111111111"
        assert _coerce_tenant_uuid(tid) == tid

    def test_accepts_uuid_object(self) -> None:
        u = uuid.uuid4()
        assert _coerce_tenant_uuid(u) == str(u)

    def test_canonicalises_uppercase(self) -> None:
        result = _coerce_tenant_uuid("AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE")
        assert result == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

    @pytest.mark.parametrize("bad", [
        "not-a-uuid",
        "'; DROP TABLE tenants; --",
        "' OR '1'='1",
        "11111111-1111-1111-1111-11111111111",  # one char short
        "",
        "11111111-1111-1111-1111-111111111111'--",
    ])
    def test_rejects_sql_injection_and_garbage(self, bad: str) -> None:
        with pytest.raises(ValueError):
            _coerce_tenant_uuid(bad)
