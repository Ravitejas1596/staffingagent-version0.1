"""Symmetric encryption for secrets at rest.

Currently scoped to Bullhorn API credentials (workstream 4 of the Security
Sprint). Uses Fernet (AES-128-CBC + HMAC-SHA256) from the `cryptography`
library, which provides authenticated encryption out of the box.

Key management
--------------
The Key Encryption Key (KEK) is a URL-safe base64-encoded 32-byte value
sourced from AWS Secrets Manager and injected into the API container as
the BULLHORN_CREDS_KEK environment variable. To rotate:

    1. Generate a new key:  Fernet.generate_key()
    2. Update the Secrets Manager secret to the new value, while leaving
       the old value available via BULLHORN_CREDS_KEK_PREVIOUS.
    3. Deploy. New writes use the new key. Reads accept either key.
    4. Run scripts/encrypt_existing_bullhorn_creds.py --rotate to re-encrypt
       every row under the new key.
    5. Remove BULLHORN_CREDS_KEK_PREVIOUS.

The MultiFernet pattern handles steps 2 and 3 transparently.

The `bullhorn_credentials_version` column on `tenants` tracks which key
generation encrypted the row, which lets the rotation script find rows
still on the old key after step 4.
"""
from __future__ import annotations

import base64
import json
import os
from functools import lru_cache
from typing import Any

from cryptography.fernet import Fernet, InvalidToken, MultiFernet


class CryptoError(RuntimeError):
    """Raised when encryption or decryption fails in a way the caller should surface."""


def _validate_key(key: str) -> bytes:
    """Fail fast on malformed keys so bad config is caught at boot, not at first use."""
    if not key:
        raise CryptoError("BULLHORN_CREDS_KEK is empty or unset")
    try:
        raw = base64.urlsafe_b64decode(key.encode())
    except Exception as exc:
        raise CryptoError("BULLHORN_CREDS_KEK is not valid url-safe base64") from exc
    if len(raw) != 32:
        raise CryptoError(
            f"BULLHORN_CREDS_KEK must decode to 32 bytes, got {len(raw)}"
        )
    return key.encode()


@lru_cache(maxsize=1)
def _get_cipher() -> MultiFernet:
    """Build a MultiFernet from BULLHORN_CREDS_KEK (+ optional PREVIOUS).

    Encryption always uses the primary key (first in the list). Decryption
    tries each key in order, which makes key rotation a no-downtime op.
    Cached per process for speed; tests should call `reset_cipher_cache()`.
    """
    primary = _validate_key(os.environ.get("BULLHORN_CREDS_KEK", ""))
    fernets = [Fernet(primary)]

    previous = os.environ.get("BULLHORN_CREDS_KEK_PREVIOUS", "")
    if previous:
        fernets.append(Fernet(_validate_key(previous)))

    return MultiFernet(fernets)


def reset_cipher_cache() -> None:
    """Drop the cached cipher. Call this after rotating KEKs in tests."""
    _get_cipher.cache_clear()


def encrypt_credentials(plaintext: dict[str, Any]) -> bytes:
    """Encrypt a credential dict as a Fernet ciphertext.

    Returns raw bytes ready to INSERT into a BYTEA column. The plaintext
    must be JSON-serializable (typically client_id / client_secret /
    api_user / api_password strings).
    """
    if not isinstance(plaintext, dict):
        raise CryptoError("encrypt_credentials expects a dict")
    data = json.dumps(plaintext, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _get_cipher().encrypt(data)


def decrypt_credentials(ciphertext: bytes | memoryview | None) -> dict[str, Any]:
    """Decrypt a Fernet ciphertext back to the original credential dict.

    Returns an empty dict if ciphertext is None / empty (convenience for
    unconfigured tenants). Raises CryptoError on tampered or wrong-key
    ciphertexts so the caller can distinguish "no credentials" from
    "credentials exist but cannot be read".
    """
    if ciphertext is None:
        return {}
    blob = bytes(ciphertext) if not isinstance(ciphertext, bytes) else ciphertext
    if not blob:
        return {}
    try:
        data = _get_cipher().decrypt(blob)
    except InvalidToken as exc:
        raise CryptoError(
            "Bullhorn credentials ciphertext could not be decrypted "
            "(key rotation or tampering?)"
        ) from exc
    return json.loads(data.decode("utf-8"))


def current_key_version() -> int:
    """Return the version number of the current primary key.

    This is the value we write to `bullhorn_credentials_version` on every
    encrypt. A rotation script looks for rows with version < current_version
    and re-encrypts them. Today we have a single version; future rotations
    bump this via an env var.
    """
    try:
        return int(os.environ.get("BULLHORN_CREDS_KEK_VERSION", "1"))
    except ValueError:
        return 1
