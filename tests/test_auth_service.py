import base64
import hashlib
import os
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
os.environ["DATABASE_URL"] = "postgresql://user:pass@localhost:5432/tests"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app.auth as auth_module  # noqa: E402  pylint: disable=wrong-import-position
from app.auth import AuthService  # noqa: E402  pylint: disable=wrong-import-position


@pytest.mark.parametrize("password", ["Admin123", "Пароль123A"])
def test_get_password_hash_roundtrip(password):
    hashed = AuthService.get_password_hash(password)
    assert isinstance(hashed, str)
    assert AuthService.verify_password(password, hashed)
    assert not AuthService.verify_password(password + "!", hashed)


@pytest.mark.skipif(auth_module.bcrypt is None, reason="bcrypt backend already unavailable")
def test_get_password_hash_fallback_to_pbkdf2(monkeypatch):
    original_bcrypt = auth_module.bcrypt

    class BrokenBcrypt(types.SimpleNamespace):
        def gensalt(self, *args, **kwargs):  # pragma: no cover - passthrough
            return original_bcrypt.gensalt(*args, **kwargs)

        def hashpw(self, *args, **kwargs):
            raise RuntimeError("boom")

        def checkpw(self, *args, **kwargs):  # pragma: no cover - passthrough
            return original_bcrypt.checkpw(*args, **kwargs)

    monkeypatch.setattr(auth_module, "bcrypt", BrokenBcrypt())

    hashed = AuthService.get_password_hash("Admin123")
    assert hashed.startswith("$pbkdf2")
    assert AuthService.verify_password("Admin123", hashed)


def test_native_pbkdf2_fallback_when_passlib_missing(monkeypatch):
    monkeypatch.setattr(auth_module, "bcrypt", None)

    def broken_hash(*_args, **_kwargs):
        raise RuntimeError("passlib pbkdf2 unavailable")

    def broken_verify(*_args, **_kwargs):
        raise RuntimeError("passlib pbkdf2 unavailable")

    if auth_module.pbkdf2_sha256 is not None:
        monkeypatch.setattr(
            auth_module.pbkdf2_sha256, "hash", broken_hash, raising=False
        )
        monkeypatch.setattr(
            auth_module.pbkdf2_sha256, "verify", broken_verify, raising=False
        )

    hashed = AuthService.get_password_hash("Admin123")
    assert hashed.startswith("$pbkdf2-sha256$native$")
    assert AuthService.verify_password("Admin123", hashed)
    assert not AuthService.verify_password("Admin123!", hashed)

def _make_werkzeug_like_hash(password: str, rounds: int = 260_000) -> str:
    salt_bytes = os.urandom(16)
    salt_b64 = base64.b64encode(salt_bytes).decode("utf-8").rstrip("=")
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_bytes, rounds)
    hash_b64 = base64.b64encode(derived).decode("utf-8").rstrip("=")
    return f"pbkdf2:sha256:{rounds}${salt_b64}${hash_b64}"


def test_verify_password_supports_werkzeug_style_hashes():
    password = "WerkzeugSecret42"
    hashed = _make_werkzeug_like_hash(password)
    assert AuthService.verify_password(password, hashed)
    assert not AuthService.verify_password(password + "!", hashed)
