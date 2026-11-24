from __future__ import annotations

from dataclasses import replace
import sqlite3

from fastapi.testclient import TestClient
import pytest

from app.config import Settings
from app.factory import create_app


def group_payload(name: str = "WZN", **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": name,
        "discord_server_id": "123456789",
        "combined_statistics": False,
        "primary_alliance_name": name,
        "primary_alliance_tag": name,
        "primary_alliance_state_id": "1001",
        "assign_legacy_events": False,
        "confirm_legacy_assignment": False,
    }
    payload.update(overrides)
    return payload


def create_onboarded_group(client: TestClient, name: str = "WZN") -> dict[str, object]:
    response = client.post("/api/v1/onboarding/groups", json=group_payload(name))
    assert response.status_code == 201, response.text
    return response.json()


def test_health_and_database_migration(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ready", "migration_version": 3}


def test_group_routes_require_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/groups").status_code == 401
    assert client.get("/api/v1/onboarding").status_code == 401
    assert client.get("/api/v1/admin/audit").status_code == 401


def test_untrusted_host_is_rejected(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"Host": "attacker.example"})
    assert response.status_code == 400


def test_production_session_cookie_flags(settings: Settings) -> None:
    production_settings = replace(settings, environment="production", secure_cookies=True)
    with TestClient(create_app(production_settings), base_url="https://testserver") as secure_client:
        response = secure_client.get("/api/v1/auth/csrf")
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "secure" in cookie and "samesite=lax" in cookie and "path=/" in cookie


def test_login_requires_csrf(client: TestClient) -> None:
    client.get("/api/v1/auth/csrf")
    response = client.post("/api/v1/auth/login", json={"password": "a sufficiently long test password"})
    assert response.status_code == 403


def test_login_is_throttled_after_repeated_failures(client: TestClient) -> None:
    for _attempt in range(5):
        csrf = client.get("/api/v1/auth/csrf").json()["csrf_token"]
        assert client.post("/api/v1/auth/login", headers={"X-CSRF-Token": csrf}, json={"password": "incorrect password"}).status_code == 401
    csrf = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    assert client.post("/api/v1/auth/login", headers={"X-CSRF-Token": csrf}, json={"password": "a sufficiently long test password"}).status_code == 429


def test_login_rotates_the_session_cookie(client: TestClient) -> None:
    csrf_response = client.get("/api/v1/auth/csrf")
    anonymous_cookie = client.cookies.get("vzn_session")
    response = client.post("/api/v1/auth/login", headers={"X-CSRF-Token": csrf_response.json()["csrf_token"]}, json={"password": "a sufficiently long test password"})
    assert response.status_code == 200
    assert client.cookies.get("vzn_session") != anonymous_cookie


def test_onboarding_creates_exactly_one_primary_and_is_repeat_safe(authenticated_client: TestClient) -> None:
    status = authenticated_client.get("/api/v1/onboarding").json()
    assert status == {"required": True, "group_count": 0, "unassigned_legacy_events": 0}
    group = create_onboarded_group(authenticated_client)
    assert group["primary_count"] == 1
    alliances = authenticated_client.get(f"/api/v1/groups/{group['id']}/alliances").json()["items"]
    assert len(alliances) == 1 and alliances[0]["alliance_type"] == "primary"
    duplicate = authenticated_client.post("/api/v1/onboarding/groups", json=group_payload())
    assert duplicate.status_code == 409


def test_group_alliance_event_scoping_and_legacy_profiles(authenticated_client: TestClient) -> None:
    group = create_onboarded_group(authenticated_client)
    group_id = group["id"]
    primary = authenticated_client.get(f"/api/v1/groups/{group_id}/alliances").json()["items"][0]
    academy = authenticated_client.post(
        f"/api/v1/groups/{group_id}/alliances", json={"name": "WZN Academy", "tag": "WZNA", "state_id": "1001"}
    )
    assert academy.status_code == 201
    player = authenticated_client.post(f"/api/v1/groups/{group_id}/players", json={"fid": "100200300", "nickname": "Arctic Fox"})
    assert player.status_code == 201
    assert player.json()["group_status"] == "unconfirmed"
    event = authenticated_client.post(
        f"/api/v1/groups/{group_id}/alliances/{primary['id']}/events",
        json={"event_type": "foundry", "occurred_on": "2026-11-24", "status": "draft"},
    )
    assert event.status_code == 201
    assert event.json()["alliance_id"] == primary["id"]
    assert authenticated_client.get(f"/api/v1/groups/{group_id}/alliances/{academy.json()['id']}/events").json()["items"] == []
    event_detail = authenticated_client.get(f"/api/v1/groups/{group_id}/events/{event.json()['id']}")
    assert event_detail.status_code == 200


def test_primary_alliance_constraint_prevents_a_second_primary(authenticated_client: TestClient, settings: Settings) -> None:
    group = create_onboarded_group(authenticated_client)
    with sqlite3.connect(settings.database_path) as database:
        with pytest.raises(sqlite3.IntegrityError):
            database.execute(
                """INSERT INTO alliances(id, group_id, name, tag, state_id, alliance_type)
                   VALUES ('second-primary', ?, 'Other', 'OTHER', '1001', 'primary')""",
                (group["id"],),
            )


def test_groups_are_isolated_and_cross_group_alliance_is_rejected(authenticated_client: TestClient) -> None:
    first = create_onboarded_group(authenticated_client)
    second = authenticated_client.post("/api/v1/groups", json=group_payload("ABC")).json()
    first_alliance = authenticated_client.get(f"/api/v1/groups/{first['id']}/alliances").json()["items"][0]
    player = authenticated_client.post(f"/api/v1/groups/{first['id']}/players", json={"fid": "same-fid", "nickname": "North"})
    assert player.status_code == 201
    assert authenticated_client.get(f"/api/v1/groups/{second['id']}/players/same-fid").status_code == 404
    assert authenticated_client.get(f"/api/v1/groups/{second['id']}/alliances/{first_alliance['id']}/events").status_code == 404
    same_fid_second = authenticated_client.post(f"/api/v1/groups/{second['id']}/players", json={"fid": "same-fid", "nickname": "North"})
    assert same_fid_second.status_code == 201


def test_combined_mode_and_archiving_do_not_delete_history(authenticated_client: TestClient) -> None:
    group = create_onboarded_group(authenticated_client)
    group_id = group["id"]
    primary = authenticated_client.get(f"/api/v1/groups/{group_id}/alliances").json()["items"][0]
    event = authenticated_client.post(
        f"/api/v1/groups/{group_id}/alliances/{primary['id']}/events",
        json={"event_type": "bear_trap", "occurred_on": "2026-11-24", "status": "draft"},
    ).json()
    updated = authenticated_client.patch(f"/api/v1/groups/{group_id}", json={"combined_statistics": True})
    assert updated.status_code == 200 and updated.json()["combined_statistics"] == 1
    assert authenticated_client.get(f"/api/v1/groups/{group_id}/events/{event['id']}").status_code == 200
    academy = authenticated_client.post(f"/api/v1/groups/{group_id}/alliances", json={"name": "Academy", "tag": "A", "state_id": "1001"}).json()
    archived = authenticated_client.patch(
        f"/api/v1/groups/{group_id}/alliances/{academy['id']}", json={"status": "archived", "confirm_archive": True}
    )
    assert archived.status_code == 200 and archived.json()["status"] == "archived"
    assert authenticated_client.get(f"/api/v1/groups/{group_id}/events/{event['id']}").status_code == 200


def test_legacy_events_require_explicit_onboarding_assignment(authenticated_client: TestClient, settings: Settings) -> None:
    with sqlite3.connect(settings.database_path) as database:
        database.execute("INSERT INTO events(id, event_type, occurred_on, status) VALUES ('legacy', 'foundry', '2026-01-01', 'draft')")
    blocked = authenticated_client.post("/api/v1/onboarding/groups", json=group_payload())
    assert blocked.status_code == 409
    assigned = authenticated_client.post(
        "/api/v1/onboarding/groups", json=group_payload(assign_legacy_events=True, confirm_legacy_assignment=True)
    )
    assert assigned.status_code == 201
    group_id = assigned.json()["id"]
    assert authenticated_client.get(f"/api/v1/groups/{group_id}/events/legacy").status_code == 200


def test_logout_invalidates_session(authenticated_client: TestClient) -> None:
    assert authenticated_client.post("/api/v1/auth/logout").status_code == 204
    assert authenticated_client.get("/api/v1/groups").status_code == 401
