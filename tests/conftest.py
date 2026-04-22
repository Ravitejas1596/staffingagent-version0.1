"""Pytest configuration.

Runs before any test collects. Sets the environment variables that the
application's `Settings` refuses to start without, so unit tests can import
app modules without needing a real deployment config.

These values are test-only. Real secrets are managed in AWS Secrets Manager.
"""
from __future__ import annotations

import os


os.environ.setdefault(
    "JWT_SECRET",
    "test-only-jwt-secret-of-sufficient-length-do-not-use-in-prod-xxxxxxxxxx",
)
