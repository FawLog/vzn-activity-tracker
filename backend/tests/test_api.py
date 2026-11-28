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
    assert response.json() == {"status": "ok", "database": "ready", "migration_version": 12}


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
    assert group["initial_sync"]["status"] == "not_configured"
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
    same_fid_second = authenticated_client.post(f"/api/v1/groups/{second['id']}/players", json={"fid": "same-fid", "nickname": "South"})
    assert same_fid_second.status_code == 201
    first_profile = authenticated_client.get(f"/api/v1/groups/{first['id']}/players/same-fid")
    second_profile = authenticated_client.get(f"/api/v1/groups/{second['id']}/players/same-fid")
    assert first_profile.json()["nickname"] == "North"
    assert second_profile.json()["nickname"] == "South"


def test_player_history_is_scoped_and_legacy_history_is_not_disclosed(
    authenticated_client: TestClient,
    settings: Settings,
) -> None:
    first = create_onboarded_group(authenticated_client)
    second = authenticated_client.post("/api/v1/groups", json=group_payload("ABC")).json()
    first_id = str(first["id"])
    second_id = str(second["id"])
    assert authenticated_client.post(
        f"/api/v1/groups/{first_id}/players", json={"fid": "shared-fid", "nickname": "WZN Fox"}
    ).status_code == 201
    with sqlite3.connect(settings.database_path) as database:
        database.execute(
            "INSERT INTO player_nicknames(player_fid, nickname) VALUES ('shared-fid', 'Legacy global nickname')"
        )
        database.execute(
            "INSERT INTO player_memberships(player_fid, joined_on) VALUES ('shared-fid', '2026-01-01')"
        )
    assert authenticated_client.post(
        f"/api/v1/groups/{second_id}/players", json={"fid": "shared-fid", "nickname": "ABC Fox"}
    ).status_code == 201

    first_profile = authenticated_client.get(f"/api/v1/groups/{first_id}/players/shared-fid")
    second_profile = authenticated_client.get(f"/api/v1/groups/{second_id}/players/shared-fid")
    assert first_profile.status_code == 200 and second_profile.status_code == 200
    assert first_profile.json()["nickname"] == "WZN Fox"
    assert second_profile.json()["nickname"] == "ABC Fox"
    assert [item["nickname"] for item in first_profile.json()["nickname_history"]] == ["WZN Fox"]
    assert [item["nickname"] for item in second_profile.json()["nickname_history"]] == ["ABC Fox"]
    assert "legacy_memberships" not in first_profile.json()
    assert "legacy_memberships" not in second_profile.json()
    second_list = authenticated_client.get(f"/api/v1/groups/{second_id}/players").json()["items"]
    assert second_list == [
        {
            "fid": "shared-fid",
            "nickname": "ABC Fox",
            "created_at": second_profile.json()["created_at"],
            "updated_at": second_profile.json()["updated_at"],
            "group_status": "unconfirmed",
            "primary_alliance_id": None,
            "primary_alliance_name": None,
        }
    ]


def test_manual_players_are_listed_as_unconfirmed_in_their_own_group(authenticated_client: TestClient) -> None:
    first = create_onboarded_group(authenticated_client)
    first_id = str(first["id"])
    second = authenticated_client.post("/api/v1/groups", json=group_payload("ABC")).json()
    second_id = str(second["id"])
    assert authenticated_client.post(
        f"/api/v1/groups/{first_id}/players", json={"fid": "manual-fid", "nickname": "WZN Manual"}
    ).status_code == 201
    first_all = authenticated_client.get(f"/api/v1/groups/{first_id}/players?affiliation=all").json()["items"]
    first_unconfirmed = authenticated_client.get(f"/api/v1/groups/{first_id}/players?affiliation=unconfirmed").json()["items"]
    primary_id = authenticated_client.get(f"/api/v1/groups/{first_id}/alliances").json()["items"][0]["id"]
    first_primary = authenticated_client.get(
        f"/api/v1/groups/{first_id}/players?affiliation=alliance&alliance_id={primary_id}"
    ).json()["items"]
    assert [(player["fid"], player["nickname"]) for player in first_all] == [("manual-fid", "WZN Manual")]
    assert [(player["fid"], player["nickname"]) for player in first_unconfirmed] == [("manual-fid", "WZN Manual")]
    assert first_primary == []
    assert authenticated_client.post(
        f"/api/v1/groups/{second_id}/players", json={"fid": "manual-fid", "nickname": "ABC Manual"}
    ).status_code == 201
    second_unconfirmed = authenticated_client.get(f"/api/v1/groups/{second_id}/players?affiliation=unconfirmed").json()["items"]
    assert [(player["fid"], player["nickname"]) for player in second_unconfirmed] == [("manual-fid", "ABC Manual")]
    assert authenticated_client.get(f"/api/v1/groups/{first_id}/players/manual-fid").json()["nickname"] == "WZN Manual"


def test_sqlite_rejects_cross_group_alliance_references(
    authenticated_client: TestClient,
    settings: Settings,
) -> None:
    first = create_onboarded_group(authenticated_client)
    second = authenticated_client.post("/api/v1/groups", json=group_payload("ABC")).json()
    first_id = str(first["id"])
    second_id = str(second["id"])
    first_alliance = authenticated_client.get(f"/api/v1/groups/{first_id}/alliances").json()["items"][0]["id"]
    second_alliance = authenticated_client.get(f"/api/v1/groups/{second_id}/alliances").json()["items"][0]["id"]
    with sqlite3.connect(settings.database_path) as database:
        database.execute("INSERT INTO players(fid, nickname) VALUES ('scope-fid', 'Scoped player')")

    rejected_statements = [
        (
            "INSERT INTO player_group_profiles(player_fid, group_id, primary_alliance_id, source_type) VALUES ('scope-fid', ?, ?, 'manual')",
            (first_id, second_alliance),
        ),
        (
            "INSERT INTO player_nickname_observations(player_fid, group_id, alliance_id, nickname, observed_at, source_type) VALUES ('scope-fid', ?, ?, 'Cross group', '2026-01-01', 'manual')",
            (first_id, second_alliance),
        ),
        (
            "INSERT INTO player_nickname_observations(player_fid, alliance_id, nickname, observed_at, source_type) VALUES ('scope-fid', ?, 'Unscoped alliance', '2026-01-01', 'manual')",
            (second_alliance,),
        ),
        (
            "INSERT INTO player_membership_observations(player_fid, group_id, alliance_id, observed_at, source_type) VALUES ('scope-fid', ?, ?, '2026-01-01', 'manual')",
            (first_id, second_alliance),
        ),
        (
            "INSERT INTO player_alliance_transitions(id, player_fid, group_id, from_alliance_id, first_observed_at, classification) VALUES ('cross-transition', 'scope-fid', ?, ?, '2026-01-01', 'temporary_pending')",
            (first_id, second_alliance),
        ),
        (
            "INSERT INTO player_alliance_transitions(id, player_fid, group_id, to_alliance_id, first_observed_at, classification) VALUES ('cross-transition-to', 'scope-fid', ?, ?, '2026-01-01', 'temporary_pending')",
            (first_id, second_alliance),
        ),
        (
            "INSERT INTO player_primary_alliance_history(player_fid, group_id, alliance_id, effective_observed_at, source_type) VALUES ('scope-fid', ?, ?, '2026-01-01', 'manual')",
            (first_id, second_alliance),
        ),
    ]
    for statement, parameters in rejected_statements:
        with sqlite3.connect(settings.database_path) as database:
            with pytest.raises(sqlite3.IntegrityError):
                database.execute(statement, parameters)

    with sqlite3.connect(settings.database_path) as database:
        database.execute(
            "INSERT INTO player_membership_observations(player_fid, group_id, alliance_id, observed_at, source_type) VALUES ('scope-fid', ?, ?, '2026-01-01', 'manual')",
            (second_id, second_alliance),
        )
        source_observation_id = database.execute("SELECT id FROM player_membership_observations").fetchone()[0]
    with sqlite3.connect(settings.database_path) as database:
        with pytest.raises(sqlite3.IntegrityError):
            database.execute(
                "INSERT INTO player_alliance_transitions(id, player_fid, group_id, first_observed_at, classification, source_observation_id) VALUES ('cross-source', 'scope-fid', ?, '2026-01-01', 'temporary_pending', ?)",
                (first_id, source_observation_id),
            )

    with sqlite3.connect(settings.database_path) as database:
        database.execute(
            "INSERT INTO player_alliance_transitions(id, player_fid, group_id, from_alliance_id, first_observed_at, classification) VALUES ('valid-transition', 'scope-fid', ?, ?, '2026-01-01', 'temporary_pending')",
            (second_id, second_alliance),
        )
    with sqlite3.connect(settings.database_path) as database:
        with pytest.raises(sqlite3.IntegrityError):
            database.execute(
                "INSERT INTO player_primary_alliance_history(player_fid, group_id, effective_observed_at, source_type, source_transition_id) VALUES ('scope-fid', ?, '2026-01-01', 'manual', 'valid-transition')",
                (first_id,),
            )

    with sqlite3.connect(settings.database_path) as database:
        with pytest.raises(sqlite3.IntegrityError):
            database.execute("UPDATE alliances SET group_id = ? WHERE id = ?", (second_id, first_alliance))


def test_archiving_rejects_new_records_and_preserves_history(authenticated_client: TestClient) -> None:
    group = create_onboarded_group(authenticated_client)
    group_id = str(group["id"])
    primary = authenticated_client.get(f"/api/v1/groups/{group_id}/alliances").json()["items"][0]
    academy = authenticated_client.post(
        f"/api/v1/groups/{group_id}/alliances", json={"name": "Academy", "tag": "A", "state_id": "1001"}
    ).json()
    historical_event = authenticated_client.post(
        f"/api/v1/groups/{group_id}/alliances/{academy['id']}/events",
        json={"event_type": "foundry", "occurred_on": "2026-11-24", "status": "draft"},
    ).json()
    assert authenticated_client.patch(
        f"/api/v1/groups/{group_id}/alliances/{academy['id']}", json={"status": "archived", "confirm_archive": True}
    ).status_code == 200
    blocked_alliance_event = authenticated_client.post(
        f"/api/v1/groups/{group_id}/alliances/{academy['id']}/events",
        json={"event_type": "foundry", "occurred_on": "2026-11-25", "status": "draft"},
    )
    assert blocked_alliance_event.status_code == 409
    assert authenticated_client.get(f"/api/v1/groups/{group_id}/events/{historical_event['id']}").status_code == 200

    assert authenticated_client.patch(
        f"/api/v1/groups/{group_id}", json={"status": "archived", "confirm_archive": True}
    ).status_code == 200
    assert authenticated_client.post(
        f"/api/v1/groups/{group_id}/players", json={"fid": "archived-player", "nickname": "Archived"}
    ).status_code == 409
    assert authenticated_client.post(
        f"/api/v1/groups/{group_id}/alliances/{primary['id']}/events",
        json={"event_type": "bear_trap", "occurred_on": "2026-11-25", "status": "draft"},
    ).status_code == 409
    assert authenticated_client.patch(f"/api/v1/groups/{group_id}", json={"combined_statistics": True}).status_code == 409
    assert authenticated_client.get(f"/api/v1/groups/{group_id}/events/{historical_event['id']}").status_code == 200

    assert authenticated_client.patch(f"/api/v1/groups/{group_id}", json={"status": "active"}).status_code == 200
    assert authenticated_client.patch(f"/api/v1/groups/{group_id}/alliances/{academy['id']}", json={"status": "active"}).status_code == 200
    assert authenticated_client.post(
        f"/api/v1/groups/{group_id}/players", json={"fid": "restored-player", "nickname": "Restored"}
    ).status_code == 201


def test_alliance_update_validates_and_persists_metadata(authenticated_client: TestClient) -> None:
    group = create_onboarded_group(authenticated_client)
    group_id = str(group["id"])
    primary = authenticated_client.get(f"/api/v1/groups/{group_id}/alliances").json()["items"][0]
    updated = authenticated_client.patch(
        f"/api/v1/groups/{group_id}/alliances/{primary['id']}",
        json={"name": "WZN Prime", "tag": "WZNP", "state_id": "1002"},
    )
    assert updated.status_code == 200
    assert {key: updated.json()[key] for key in ("name", "tag", "state_id", "alliance_type")} == {
        "name": "WZN Prime", "tag": "WZNP", "state_id": "1002", "alliance_type": "primary"
    }
    invalid = authenticated_client.patch(
        f"/api/v1/groups/{group_id}/alliances/{primary['id']}", json={"tag": "   "}
    )
    assert invalid.status_code == 422


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

def test_version_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/version").status_code == 401


def test_version_returns_only_valid_sha(authenticated_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VZN_IMAGE_TAG", "ci-" + "a"*40)
    response = authenticated_client.get("/api/v1/version")
    assert response.json() == {"sha": "a"*40}
    assert response.headers["cache-control"] == "no-store"
    monkeypatch.setenv("VZN_IMAGE_TAG", "invalid")
    assert authenticated_client.get("/api/v1/version").json() == {"sha": None}
