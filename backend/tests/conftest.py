from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.factory import create_app
from app.security import hash_password


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        app_name="VZN Test",
        environment="test",
        database_path=str(tmp_path / "test.sqlite3"),
        session_secret="test-session-secret-with-at-least-32-characters",
        admin_password_hash=hash_password("a sufficiently long test password"),
        allowed_hosts=("testserver", "localhost"),
        trusted_proxies=("testclient",),
        secure_cookies=False,
        session_ttl_seconds=3600,
        login_window_seconds=900,
        login_max_attempts=5,
    )


@pytest.fixture
def client(settings: Settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def authenticated_client(client: TestClient) -> TestClient:
    csrf = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    response = client.post(
        "/api/v1/auth/login",
        headers={"X-CSRF-Token": csrf},
        json={"password": "a sufficiently long test password"},
    )
    assert response.status_code == 200
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return client
