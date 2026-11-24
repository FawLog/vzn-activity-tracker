from __future__ import annotations

from dataclasses import replace

from fastapi.testclient import TestClient

from app.config import Settings
from app.factory import create_app


def test_health_and_database_migration(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ready", "migration_version": 2}


def test_admin_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/players").status_code == 401
    assert client.get("/api/v1/admin/audit").status_code == 401


def test_untrusted_host_is_rejected(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"Host": "attacker.example"})

    assert response.status_code == 400


def test_production_session_cookie_flags(settings: Settings) -> None:
    production_settings = replace(settings, environment="production", secure_cookies=True)
    with TestClient(
        create_app(production_settings),
        base_url="https://testserver",
    ) as secure_client:
        response = secure_client.get("/api/v1/auth/csrf")

    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "secure" in cookie
    assert "samesite=lax" in cookie
    assert "path=/" in cookie


def test_login_requires_csrf(client: TestClient) -> None:
    client.get("/api/v1/auth/csrf")
    response = client.post(
        "/api/v1/auth/login",
        json={"password": "a sufficiently long test password"},
    )
    assert response.status_code == 403


def test_login_is_throttled_after_repeated_failures(client: TestClient) -> None:
    for _attempt in range(5):
        csrf = client.get("/api/v1/auth/csrf").json()["csrf_token"]
        response = client.post(
            "/api/v1/auth/login",
            headers={"X-CSRF-Token": csrf},
            json={"password": "incorrect password"},
        )
        assert response.status_code == 401

    csrf = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    blocked = client.post(
        "/api/v1/auth/login",
        headers={"X-CSRF-Token": csrf},
        json={"password": "a sufficiently long test password"},
    )
    assert blocked.status_code == 429


def test_login_rotates_the_session_cookie(client: TestClient) -> None:
    csrf_response = client.get("/api/v1/auth/csrf")
    anonymous_cookie = client.cookies.get("vzn_session")
    response = client.post(
        "/api/v1/auth/login",
        headers={"X-CSRF-Token": csrf_response.json()["csrf_token"]},
        json={"password": "a sufficiently long test password"},
    )

    assert response.status_code == 200
    assert client.cookies.get("vzn_session") != anonymous_cookie


def test_authenticated_mutation_requires_csrf(authenticated_client: TestClient) -> None:
    response = authenticated_client.post(
        "/api/v1/players",
        headers={"X-CSRF-Token": ""},
        json={"fid": "csrf-check", "nickname": "CSRF Check"},
    )

    assert response.status_code == 403


def test_create_player_event_and_audit(authenticated_client: TestClient) -> None:
    player = authenticated_client.post(
        "/api/v1/players",
        json={"fid": "100200300", "nickname": "Arctic Fox"},
    )
    assert player.status_code == 201
    assert player.json()["fid"] == "100200300"
    assert player.json()["nickname_history"][0]["nickname"] == "Arctic Fox"

    duplicate = authenticated_client.post(
        "/api/v1/players",
        json={"fid": "100200300", "nickname": "Other"},
    )
    assert duplicate.status_code == 409

    event = authenticated_client.post(
        "/api/v1/events",
        json={"event_type": "svs_preparation", "occurred_on": "2026-11-24", "status": "draft"},
    )
    assert event.status_code == 201
    assert event.json()["participants"] == []

    overview = authenticated_client.get("/api/v1/overview").json()
    assert overview["players"] == 1
    assert overview["events"] == 1
    assert overview["published_events"] == 0

    audit = authenticated_client.get("/api/v1/admin/audit").json()["items"]
    assert [item["entity_type"] for item in audit] == ["event", "player"]


def test_logout_invalidates_session(authenticated_client: TestClient) -> None:
    assert authenticated_client.post("/api/v1/auth/logout").status_code == 204
    assert authenticated_client.get("/api/v1/players").status_code == 401
