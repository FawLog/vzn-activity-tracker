from __future__ import annotations

import pytest

from app.config import load_settings
from app.security import hash_password


def test_production_rejects_insecure_session_cookie(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret-with-at-least-32-characters")
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", hash_password("a sufficiently long test password"))
    monkeypatch.setenv("ALLOWED_HOSTS", "vzn.example.test")
    monkeypatch.setenv("SECURE_COOKIES", "0")

    with pytest.raises(RuntimeError, match="SECURE_COOKIES"):
        load_settings()


def test_malformed_administrator_hash_fails_at_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret-with-at-least-32-characters")
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", "scrypt$invalid")

    with pytest.raises(RuntimeError, match="ADMIN_PASSWORD_HASH"):
        load_settings()
