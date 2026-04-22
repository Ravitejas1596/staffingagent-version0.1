"""Verify that the Settings object refuses weak JWT secrets at boot.

These tests exercise the field_validator directly so they do not need to
reload the module under test. The production application inherits the
same validator.
"""
from __future__ import annotations

import importlib

import pytest
from pydantic import ValidationError


def _fresh_settings_class():
    """Re-import the module so we get a fresh Settings class that will
    re-run validators when we instantiate it."""
    from app_platform.api import config as cfg
    importlib.reload(cfg)
    return cfg.Settings


@pytest.mark.parametrize("bad", [
    "",
    "change-me-in-production",
    "changeme",
    "secret",
    "short",
    "a" * 31,  # one char below the 32-char floor
])
def test_weak_secrets_rejected(monkeypatch, bad: str) -> None:
    monkeypatch.setenv("JWT_SECRET", bad)
    # The module-level `settings = Settings()` in config.py fires during
    # importlib.reload, so the ValidationError is raised there — not in cls().
    with pytest.raises(ValidationError):
        _fresh_settings_class()


def test_strong_secret_accepted(monkeypatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "A" * 48)
    cls = _fresh_settings_class()
    instance = cls()
    assert len(instance.jwt_secret) >= 32


def test_access_token_ttl_is_60_min(monkeypatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "A" * 48)
    cls = _fresh_settings_class()
    instance = cls()
    assert instance.jwt_expire_minutes == 60
