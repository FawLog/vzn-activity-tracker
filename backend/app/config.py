"""Validated runtime configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass

from .security import password_hash_is_valid


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    app_name: str
    environment: str
    database_path: str
    session_secret: str
    admin_password_hash: str
    allowed_hosts: tuple[str, ...]
    trusted_proxies: tuple[str, ...]
    secure_cookies: bool
    session_ttl_seconds: int
    login_window_seconds: int
    login_max_attempts: int

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


def load_settings() -> Settings:
    session_secret = os.getenv("SESSION_SECRET", "")
    if len(session_secret) < 32:
        raise RuntimeError("SESSION_SECRET must contain at least 32 characters")

    password_hash = os.getenv("ADMIN_PASSWORD_HASH", "")
    if not password_hash_is_valid(password_hash):
        raise RuntimeError("ADMIN_PASSWORD_HASH is missing or invalid")

    allowed_hosts = _csv(os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1"))
    if not allowed_hosts or any("*" in host for host in allowed_hosts):
        raise RuntimeError("ALLOWED_HOSTS must contain explicit hostnames")

    environment = os.getenv("APP_ENV", "production").strip().lower()
    if environment not in {"development", "test", "production"}:
        raise RuntimeError("APP_ENV must be development, test, or production")

    secure_cookies = _as_bool(os.getenv("SECURE_COOKIES", "1"))
    if environment == "production" and not secure_cookies:
        raise RuntimeError("SECURE_COOKIES must be enabled in production")

    session_ttl_seconds = int(os.getenv("SESSION_TTL_SECONDS", "28800"))
    login_window_seconds = int(os.getenv("LOGIN_WINDOW_SECONDS", "900"))
    login_max_attempts = int(os.getenv("LOGIN_MAX_ATTEMPTS", "5"))
    if min(session_ttl_seconds, login_window_seconds, login_max_attempts) < 1:
        raise RuntimeError("Session and login security limits must be positive")

    return Settings(
        app_name=os.getenv("APP_NAME", "VZN Activity Tracker"),
        environment=environment,
        database_path=os.getenv("DATABASE_PATH", "/data/vzn.sqlite3"),
        session_secret=session_secret,
        admin_password_hash=password_hash,
        allowed_hosts=allowed_hosts,
        trusted_proxies=_csv(os.getenv("TRUSTED_PROXIES", "127.0.0.1,::1")),
        secure_cookies=secure_cookies,
        session_ttl_seconds=session_ttl_seconds,
        login_window_seconds=login_window_seconds,
        login_max_attempts=login_max_attempts,
    )
