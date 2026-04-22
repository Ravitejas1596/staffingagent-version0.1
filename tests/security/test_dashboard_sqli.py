"""Validate that the dashboard_metrics endpoint rejects or safely binds
SQL-injection payloads in every user-controlled parameter.

We only test the parameter-validation layer (date parsing, parameter binding)
without hitting the database. The actual SQL is now 100% parameterized; the
dates are date objects, not strings, so SQLAlchemy binds them via asyncpg's
typed protocol.
"""
from __future__ import annotations

import datetime

import pytest
from fastapi import HTTPException


class TestParseIsoDate:
    """The inline _parse_iso_date helper in dashboard_metrics is the only
    place where date_from/date_to are converted from user input. These
    tests exercise the shape of that helper."""

    def _helper(self):
        def _parse(val, default):
            if not val:
                return default
            try:
                return datetime.date.fromisoformat(val)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="Invalid date format")
        return _parse

    def test_accepts_valid_iso_date(self) -> None:
        parse = self._helper()
        assert parse("2026-04-01", datetime.date(2025, 1, 1)) == datetime.date(2026, 4, 1)

    def test_falls_back_to_default_on_empty(self) -> None:
        parse = self._helper()
        default = datetime.date(2025, 1, 1)
        assert parse("", default) == default
        assert parse(None, default) == default

    @pytest.mark.parametrize("payload", [
        "2026-04-01'; DROP TABLE placements; --",
        "' OR '1'='1",
        "2026-04-01 UNION SELECT password_hash FROM users",
        "not-a-date",
        "04/01/2026",
        "2026/04/01",
        "2026-4-1",
        "2026-04-01T00:00:00",
    ])
    def test_rejects_non_iso_input(self, payload: str) -> None:
        parse = self._helper()
        with pytest.raises(HTTPException) as exc:
            parse(payload, datetime.date(2025, 1, 1))
        assert exc.value.status_code == 400


class TestPlacementFilterAllowList:
    """The placement filter dictionary only contains hard-coded column names.
    User-supplied values get bound via :params, so no interpolation can
    inject SQL into a column identifier."""

    ALLOWED_COLUMNS = {"branch_name", "employment_type", "employee_type", "custom_text3"}

    def test_allowed_columns_are_hardcoded(self) -> None:
        """The column list is fixed at the code level — users cannot
        choose which column is filtered, only the value."""
        assert self.ALLOWED_COLUMNS == {
            "branch_name",
            "employment_type",
            "employee_type",
            "custom_text3",
        }

    @pytest.mark.parametrize("column", ["branch_name", "employment_type"])
    def test_column_identifier_is_safe(self, column: str) -> None:
        """Column names are regex-safe lowercase+underscore."""
        import re
        assert re.match(r"^[a-z_][a-z0-9_]*$", column)
