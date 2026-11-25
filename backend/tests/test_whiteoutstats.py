from __future__ import annotations

from dataclasses import replace
import sqlite3
from typing import Any

from fastapi.testclient import TestClient

from app.config import Settings
from app.factory import create_app
from app.schemas import AllianceCreate, GroupCreate
from app.services import groups, records, whiteoutstats


class FakeFetcher:
    def __init__(self, *responses: whiteoutstats.ProviderResponse):
        self.responses = list(responses)
        self.calls: list[tuple[str, str, int]] = []

    def fetch(self, state_id: str, tag: str, *, wait: int) -> whiteoutstats.ProviderResponse:
        self.calls.append((state_id, tag, wait))
        return self.responses.pop(0)


def payload(*, cached_at: str = "2026-01-01T00:00:00Z", members: list[dict[str, Any]] | None = None, kid: str = "1001") -> dict[str, Any]:
    roster = members if members is not None else [{"fid": "101", "uid": "u101", "nick_name": "North", "power": 100, "kills": 12, "furnace_level": 30, "alliance_rank": 4, "kid": kid, "avatar_url": "https://example.test/a.png"}]
    return {"ok": True, "fresh": True, "cached_at": cached_at, "refresh": "done", "alliance": {"aid": "a1", "name": "VZN", "abbr": "VZN", "kid": kid, "power": 1000, "count": len(roster), "leader_name": "North", "leader_chief_id": "101", "flag_url": "https://example.test/f.png", "power_rank": 2}, "members": roster}


def setup_alliance(settings: Settings, *, name: str = "VZN", state: str = "1001", onboarding: bool = True) -> tuple[str, str]:
    group = groups.create_group(settings.database_path, GroupCreate(name=name, primary_alliance_name=name, primary_alliance_tag=name, primary_alliance_state_id=state), onboarding=onboarding, sync_enabled=True)
    alliance = groups.list_alliances(settings.database_path, str(group["id"]))[0]
    return str(group["id"]), str(alliance["id"])


def synced(settings: Settings, group_id: str, alliance_id: str, response: dict[str, Any], *, trigger: str = "scheduled") -> whiteoutstats.SyncResult:
    return whiteoutstats.sync_alliance(settings.database_path, settings, group_id, alliance_id, trigger_type=trigger, fetcher=FakeFetcher(whiteoutstats.ProviderResponse(200, response)))


def test_first_successful_roster_import_of_100_members(settings: Settings) -> None:
    configured = replace(settings, whiteoutstats_api_key="test-key")
    group_id, alliance_id = setup_alliance(configured)
    members = [{"fid": str(index), "nick_name": f"Member {index}", "power": index, "kills": index + 1, "furnace_level": 30, "alliance_rank": 4, "kid": "1001"} for index in range(1, 101)]
    result = synced(configured, group_id, alliance_id, payload(members=members))
    assert (result.status, result.found_count, result.added_count) == ("success", 100, 100)
    roster = records.list_players(configured.database_path, group_id, limit=250)
    assert roster is not None and roster["total"] == 100


def test_repeat_cached_roster_does_not_duplicate_observations(settings: Settings) -> None:
    configured = replace(settings, whiteoutstats_api_key="test-key")
    group_id, alliance_id = setup_alliance(configured)
    assert synced(configured, group_id, alliance_id, payload()).status == "success"
    stale = dict(payload())
    stale.update({"fresh": False, "refresh": "queued", "retry_after": 60})
    result = synced(configured, group_id, alliance_id, stale)
    assert result.status == "partial"
    with sqlite3.connect(configured.database_path) as database:
        assert database.execute("SELECT COUNT(*) FROM player_game_stat_snapshots").fetchone()[0] == 1
        assert database.execute("SELECT COUNT(*) FROM player_membership_observations").fetchone()[0] == 1


def test_nickname_and_game_stat_changes_are_historic(settings: Settings) -> None:
    configured = replace(settings, whiteoutstats_api_key="test-key")
    group_id, alliance_id = setup_alliance(configured)
    assert synced(configured, group_id, alliance_id, payload()).status == "success"
    changed = payload(cached_at="2026-01-02T00:00:00Z", members=[{"fid": "101", "uid": "u101", "nick_name": "Northern Fox", "power": 120, "kills": 17, "furnace_level": 31, "alliance_rank": 3, "kid": "1001"}])
    assert synced(configured, group_id, alliance_id, changed).status == "success"
    player = records.get_player(configured.database_path, group_id, "101")
    assert player is not None and player["nickname"] == "Northern Fox" and player["power"] == 120
    assert len(player["nickname_history"]) == 2 and len(player["stat_history"]) == 2


def test_missing_from_roster_is_only_an_absence_observation(settings: Settings) -> None:
    configured = replace(settings, whiteoutstats_api_key="test-key")
    group_id, alliance_id = setup_alliance(configured)
    first = payload(members=[{"fid": "101", "nick_name": "North", "power": 1, "kills": 1, "furnace_level": 1, "alliance_rank": 4, "kid": "1001"}, {"fid": "102", "nick_name": "South", "power": 2, "kills": 2, "furnace_level": 2, "alliance_rank": 4, "kid": "1001"}])
    assert synced(configured, group_id, alliance_id, first).status == "success"
    assert synced(configured, group_id, alliance_id, payload(cached_at="2026-01-02T00:00:00Z", members=[first["members"][0]])).status == "success"
    with sqlite3.connect(configured.database_path) as database:
        assert database.execute("SELECT COUNT(*) FROM player_roster_absence_observations WHERE player_fid = '102'").fetchone()[0] == 1
        assert database.execute("SELECT primary_alliance_id FROM player_group_profiles WHERE player_fid = '102'").fetchone()[0] == alliance_id


def test_temporary_then_permanent_transfer_after_48_hours(settings: Settings) -> None:
    configured = replace(settings, whiteoutstats_api_key="test-key")
    group_id, primary_id = setup_alliance(configured)
    additional = groups.create_additional_alliance(configured.database_path, group_id, AllianceCreate(name="Academy", tag="ACA", state_id="1001"), sync_enabled=True)
    assert additional is not None
    academy_id = str(additional["id"])
    assert synced(configured, group_id, primary_id, payload(cached_at="2026-01-01T00:00:00Z")).status == "success"
    assert synced(configured, group_id, academy_id, payload(cached_at="2026-01-02T00:00:00Z")).status == "success"
    with sqlite3.connect(configured.database_path) as database:
        transition = database.execute("SELECT classification FROM player_alliance_transitions").fetchone()[0]
        profile = database.execute("SELECT primary_alliance_id FROM player_group_profiles WHERE player_fid = '101'").fetchone()[0]
    assert transition == "temporary_pending" and profile == primary_id
    assert synced(configured, group_id, academy_id, payload(cached_at="2026-01-04T01:00:00Z")).status == "success"
    with sqlite3.connect(configured.database_path) as database:
        assert database.execute("SELECT classification FROM player_alliance_transitions").fetchone()[0] == "permanent"
        assert database.execute("SELECT primary_alliance_id FROM player_group_profiles WHERE player_fid = '101'").fetchone()[0] == academy_id


def test_state_change_confirms_transfer_immediately_and_groups_stay_isolated(settings: Settings) -> None:
    configured = replace(settings, whiteoutstats_api_key="test-key")
    group_id, primary_id = setup_alliance(configured)
    moved = groups.create_additional_alliance(configured.database_path, group_id, AllianceCreate(name="Moved", tag="MOV", state_id="1002"), sync_enabled=True)
    assert moved is not None
    assert synced(configured, group_id, primary_id, payload()).status == "success"
    assert synced(configured, group_id, str(moved["id"]), payload(cached_at="2026-01-01T01:00:00Z", kid="1002")).status == "success"
    other_group, other_alliance = setup_alliance(configured, name="OTHER", onboarding=False)
    assert synced(configured, other_group, other_alliance, payload()).status == "success"
    with sqlite3.connect(configured.database_path) as database:
        assert database.execute("SELECT classification FROM player_alliance_transitions WHERE group_id = ?", (group_id,)).fetchone()[0] == "permanent"
        assert database.execute("SELECT COUNT(*) FROM player_group_profiles WHERE player_fid = '101'").fetchone()[0] == 2


def test_202_429_and_invalid_roster_release_the_sync_lock(settings: Settings) -> None:
    configured = replace(settings, whiteoutstats_api_key="test-key")
    group_id, alliance_id = setup_alliance(configured)
    for response, expected in [
        (whiteoutstats.ProviderResponse(202, {"pending": True}, 10), "partial"),
        (whiteoutstats.ProviderResponse(429, {}, 20), "rate_limited"),
        (whiteoutstats.ProviderResponse(200, {"fresh": True, "alliance": {}, "members": "bad"}), "failed"),
    ]:
        result = whiteoutstats.sync_alliance(configured.database_path, configured, group_id, alliance_id, trigger_type="scheduled", fetcher=FakeFetcher(response))
        assert result.status == expected
        with sqlite3.connect(configured.database_path) as database:
            assert database.execute("SELECT sync_in_progress_at FROM alliance_sync_settings WHERE alliance_id = ?", (alliance_id,)).fetchone()[0] is None


def test_sync_routes_are_admin_and_csrf_protected(settings: Settings, monkeypatch) -> None:
    configured = replace(settings, whiteoutstats_api_key="test-key")
    monkeypatch.setattr(
        whiteoutstats,
        "WhiteoutStatsClient",
        lambda _settings: FakeFetcher(whiteoutstats.ProviderResponse(200, payload())),
    )
    with TestClient(create_app(configured)) as client:
        assert client.get("/api/v1/groups/x/alliances/y/sync").status_code == 401
        csrf = client.get("/api/v1/auth/csrf").json()["csrf_token"]
        login = client.post("/api/v1/auth/login", headers={"X-CSRF-Token": csrf}, json={"password": "a sufficiently long test password"})
        assert login.status_code == 200
        csrf = login.json()["csrf_token"]
        group = client.post("/api/v1/onboarding/groups", headers={"X-CSRF-Token": csrf}, json={"name": "VZN", "primary_alliance_name": "VZN", "primary_alliance_tag": "VZN", "primary_alliance_state_id": "1001"})
        assert group.status_code == 201
        alliance_id = client.get(f"/api/v1/groups/{group.json()['id']}/alliances").json()["items"][0]["id"]
        assert client.get(f"/api/v1/groups/{group.json()['id']}/alliances/{alliance_id}/sync").status_code == 200
        assert client.post(f"/api/v1/groups/{group.json()['id']}/alliances/{alliance_id}/sync").status_code == 403
