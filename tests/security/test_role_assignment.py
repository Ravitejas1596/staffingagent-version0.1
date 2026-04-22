"""Verify the role-assignment guard blocks privilege-escalation attempts."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app_platform.api.users import assert_can_assign_role


class TestSuperAdminGrant:
    @pytest.mark.parametrize("caller_role", ["viewer", "manager", "admin", "super_admin"])
    def test_super_admin_not_grantable_by_anyone(self, caller_role: str) -> None:
        with pytest.raises(HTTPException) as exc:
            assert_can_assign_role(
                caller_role=caller_role,
                target_role="super_admin",
                caller_sub="caller-id",
            )
        assert exc.value.status_code == 403


class TestHierarchy:
    @pytest.mark.parametrize("caller_role,target_role", [
        ("viewer", "manager"),
        ("viewer", "admin"),
        ("manager", "admin"),
    ])
    def test_cannot_assign_higher_role(self, caller_role: str, target_role: str) -> None:
        with pytest.raises(HTTPException) as exc:
            assert_can_assign_role(
                caller_role=caller_role,
                target_role=target_role,
                caller_sub="caller-id",
            )
        assert exc.value.status_code == 403

    @pytest.mark.parametrize("caller_role,target_role", [
        ("manager", "viewer"),
        ("manager", "manager"),
        ("admin", "viewer"),
        ("admin", "manager"),
        ("admin", "admin"),
        ("super_admin", "admin"),
        ("super_admin", "manager"),
        ("super_admin", "viewer"),
    ])
    def test_can_assign_equal_or_lower_role(self, caller_role: str, target_role: str) -> None:
        assert_can_assign_role(
            caller_role=caller_role,
            target_role=target_role,
            caller_sub="caller-id",
        )


class TestSelfPromotion:
    def test_cannot_change_own_role(self) -> None:
        with pytest.raises(HTTPException) as exc:
            assert_can_assign_role(
                caller_role="admin",
                target_role="admin",
                caller_sub="user-123",
                target_user_id="user-123",
            )
        assert exc.value.status_code == 403
        assert "own role" in exc.value.detail.lower()

    def test_changing_other_user_is_ok(self) -> None:
        assert_can_assign_role(
            caller_role="admin",
            target_role="manager",
            caller_sub="user-123",
            target_user_id="user-456",
        )


class TestInvalidRoles:
    def test_invalid_role_string_rejected(self) -> None:
        with pytest.raises(HTTPException) as exc:
            assert_can_assign_role(
                caller_role="admin",
                target_role="root",
                caller_sub="x",
            )
        assert exc.value.status_code == 422
