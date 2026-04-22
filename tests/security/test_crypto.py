"""Unit tests for app_platform.api.crypto.

Verifies:
- Round-trip encryption/decryption
- Different ciphertexts for same plaintext (Fernet uses random IV)
- Tampered ciphertext is rejected
- MultiFernet can decrypt with a rotated-out key
- Missing KEK fails fast with a useful error
"""
from __future__ import annotations

import base64
import os

import pytest
from cryptography.fernet import Fernet


@pytest.fixture(autouse=True)
def _kek(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("BULLHORN_CREDS_KEK", key)
    monkeypatch.delenv("BULLHORN_CREDS_KEK_PREVIOUS", raising=False)

    from app_platform.api import crypto
    crypto.reset_cipher_cache()
    yield key
    crypto.reset_cipher_cache()


def test_round_trip():
    from app_platform.api.crypto import decrypt_credentials, encrypt_credentials

    creds = {
        "client_id": "my_client_id",
        "client_secret": "super_secret_value",
        "api_user": "bullhorn_api_user",
        "api_password": "p@ssw0rd!",
    }
    ct = encrypt_credentials(creds)
    assert isinstance(ct, bytes)
    assert b"client_secret" not in ct, "plaintext must not appear in ciphertext"

    recovered = decrypt_credentials(ct)
    assert recovered == creds


def test_ciphertext_is_randomized():
    from app_platform.api.crypto import encrypt_credentials

    ct1 = encrypt_credentials({"k": "v"})
    ct2 = encrypt_credentials({"k": "v"})
    assert ct1 != ct2, "Fernet should use a random IV"


def test_tampered_ciphertext_raises():
    from app_platform.api.crypto import CryptoError, decrypt_credentials, encrypt_credentials

    ct = bytearray(encrypt_credentials({"k": "v"}))
    ct[-5] ^= 0xFF  # flip a byte in the MAC
    with pytest.raises(CryptoError):
        decrypt_credentials(bytes(ct))


def test_empty_ciphertext_returns_empty_dict():
    from app_platform.api.crypto import decrypt_credentials

    assert decrypt_credentials(None) == {}
    assert decrypt_credentials(b"") == {}


def test_rotation_old_key_still_decrypts(monkeypatch):
    """After rotation, ciphertext encrypted under the old key must still read."""
    from app_platform.api import crypto
    from app_platform.api.crypto import decrypt_credentials, encrypt_credentials

    ct_old_era = encrypt_credentials({"secret": "old"})

    new_key = Fernet.generate_key().decode()
    old_key = os.environ["BULLHORN_CREDS_KEK"]
    monkeypatch.setenv("BULLHORN_CREDS_KEK", new_key)
    monkeypatch.setenv("BULLHORN_CREDS_KEK_PREVIOUS", old_key)
    crypto.reset_cipher_cache()

    recovered = decrypt_credentials(ct_old_era)
    assert recovered == {"secret": "old"}


def test_missing_kek_fails_loudly(monkeypatch):
    from app_platform.api import crypto
    from app_platform.api.crypto import CryptoError, encrypt_credentials

    monkeypatch.delenv("BULLHORN_CREDS_KEK", raising=False)
    crypto.reset_cipher_cache()
    with pytest.raises(CryptoError):
        encrypt_credentials({"k": "v"})


def test_malformed_kek_rejected(monkeypatch):
    from app_platform.api import crypto
    from app_platform.api.crypto import CryptoError, encrypt_credentials

    monkeypatch.setenv("BULLHORN_CREDS_KEK", "not-a-valid-fernet-key")
    crypto.reset_cipher_cache()
    with pytest.raises(CryptoError):
        encrypt_credentials({"k": "v"})


def test_kek_wrong_length_rejected(monkeypatch):
    """A 16-byte base64 payload should be rejected even though it is valid base64."""
    from app_platform.api import crypto
    from app_platform.api.crypto import CryptoError, encrypt_credentials

    short = base64.urlsafe_b64encode(b"x" * 16).decode()
    monkeypatch.setenv("BULLHORN_CREDS_KEK", short)
    crypto.reset_cipher_cache()
    with pytest.raises(CryptoError):
        encrypt_credentials({"k": "v"})
