from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
import sqlite3
from typing import Any

from fastapi.testclient import TestClient
import pytest

from app.config import Settings
from app import database
from app.factory import create_app
from app.schemas import AllianceCreate, AllianceUpdate, GroupCreate, PlayerCreate
from app.services import groups, records, whiteoutstats


class FakeFetcher:
    def __init__(self, *responses: whiteoutstats.ProviderResponse):
        self.responses = list(responses)
        self.calls: list[tuple[str, str, int]] = []

    def fetch(self, state_id: str, tag: str, *, wait: int) -> whiteoutstats.ProviderResponse:
        self.calls.append((state_id, tag, wait))
        return self.responses.pop(0)

    def fetch_info(self, state_id: str, tag: str) -> whiteoutstats.ProviderResponse:
        self.calls.append((state_id, tag, 0))
        return self.responses.pop(0)


def test_provider_client_sends_identifying_user_agent(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class Response:
        status = 200
        headers: dict[str, str] = {}

        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"ok": true, "alliance": {"aid": "a1"}}'

    def fake_urlopen(request: object, *, timeout: int) -> Response:
        captured["request"] = request
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(whiteoutstats, "urlopen", fake_urlopen)
    configured = replace(settings, whiteoutstats_api_key="test-key")

    response = whiteoutstats.WhiteoutStatsClient(configured).fetch_info("4284", "VZN")

    request = captured["request"]
    assert response.status_code == 200
    assert captured["timeout"] == configured.whiteoutstats_timeout_seconds
    assert getattr(request, "full_url") == "https://api.whiteoutstats.com/v1/alliances/4284/VZN?include=info"
    assert getattr(request, "get_header")("User-agent") == whiteoutstats.WHITEOUTSTATS_USER_AGENT
    assert getattr(request, "get_header")("Authorization") == "Bearer test-key"


def payload(*, cached_at: object = "2026-01-01T00:00:00Z", members: list[dict[str, Any]] | None = None, kid: str = "1001", count: int | None = None) -> dict[str, Any]:
    roster = members if members is not None else [{"fid": "101", "uid": "u101", "nick_name": "North", "power": 100, "kills": 12, "furnace_level": 30, "alliance_rank": 4, "kid": kid, "avatar_url": "https://example.test/a.png"}]
    return {"ok": True, "fresh": True, "cached_at": cached_at, "refresh": "done", "alliance": {"aid": "a1", "name": "VZN", "abbr": "VZN", "kid": kid, "power": 1000, "count": len(roster) if count is None else count, "leader_name": "North", "leader_chief_id": "101", "flag_url": "https://example.test/f.png", "power_rank": 2}, "members": roster}


def setup_alliance(settings: Settings, *, name: str = "VZN", state: str = "1001", onboarding: bool = True) -> tuple[str, str]:
    database.migrate(settings.database_path)
    group = groups.create_group(settings.database_path, GroupCreate(name=name, primary_alliance_name=name, primary_alliance_tag=name, primary_alliance_state_id=state), onboarding=onboarding, sync_enabled=True)
    alliance = groups.list_alliances(settings.database_path, str(group["id"]))[0]
    groups.connect_whiteoutstats_alliance(
        settings.database_path,
        str(group["id"]),
        str(alliance["id"]),
        "a1",
        sync_enabled=True,
    )
    return str(group["id"]), str(alliance["id"])


def connect_alliance(settings: Settings, group_id: str, alliance_id: str, aid: str = "a1") -> None:
    assert groups.connect_whiteoutstats_alliance(
        settings.database_path,
        group_id,
        alliance_id,
        aid,
        sync_enabled=True,
    ) is not None


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


def test_roster_column_sorting_before_pagination(settings: Settings) -> None:
    configured = replace(settings, whiteoutstats_api_key="test-key")
    group_id, alliance_id = setup_alliance(configured)
    members = [
        {"fid": "101", "nick_name": "North", "power": 20, "kills": 300, "furnace_level": 30, "alliance_rank": 2, "kid": "1001"},
        {"fid": "102", "nick_name": "South", "power": 100, "kills": 10, "furnace_level": 9, "alliance_rank": "R5", "kid": "1001"},
        {"fid": "103", "nick_name": "West", "power": 3, "kills": 40, "furnace_level": 20, "alliance_rank": 3, "kid": "1001"},
    ]
    assert synced(configured, group_id, alliance_id, payload(members=members)).status == "success"
    records.create_player(configured.database_path, group_id, PlayerCreate(fid="104", nickname="Unconfirmed"))
    for column, ascending in {
        "power": ["103", "101", "102"],
        "kills": ["102", "103", "101"],
        "furnace_level": ["102", "103", "101"],
        "alliance_rank": ["101", "103", "102"],
    }.items():
        for direction, expected in (("asc", ascending), ("desc", ascending[::-1])):
            first = records.list_players(configured.database_path, group_id, sort=column, direction=direction, limit=2)
            second = records.list_players(configured.database_path, group_id, sort=column, direction=direction, limit=2, offset=2)
            assert first is not None and second is not None
            assert [row["fid"] for row in first["items"] + second["items"]] == expected + ["104"]


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


def test_incomplete_roster_never_creates_absence_observations(settings: Settings) -> None:
    configured = replace(settings, whiteoutstats_api_key="test-key")
    group_id, alliance_id = setup_alliance(configured)
    first = payload(members=[{"fid": "101", "nick_name": "North", "power": 1, "kills": 1, "furnace_level": 1, "alliance_rank": 4, "kid": "1001"}, {"fid": "102", "nick_name": "South", "power": 2, "kills": 2, "furnace_level": 2, "alliance_rank": 4, "kid": "1001"}])
    assert synced(configured, group_id, alliance_id, first).status == "success"
    incomplete = payload(cached_at="2026-01-02T00:00:00Z", members=[first["members"][0]], count=2)
    assert synced(configured, group_id, alliance_id, incomplete).status == "success"
    with sqlite3.connect(configured.database_path) as database:
        assert database.execute("SELECT COUNT(*) FROM player_roster_absence_observations").fetchone()[0] == 0
        assert database.execute("SELECT roster_complete FROM alliance_stat_snapshots ORDER BY source_observed_at DESC LIMIT 1").fetchone()[0] == 0


def test_roster_without_count_never_creates_absence_observations(settings: Settings) -> None:
    configured = replace(settings, whiteoutstats_api_key="test-key")
    group_id, alliance_id = setup_alliance(configured)
    first = payload(members=[{"fid": "101", "nick_name": "North", "power": 1, "kills": 1, "furnace_level": 1, "alliance_rank": 4, "kid": "1001"}, {"fid": "102", "nick_name": "South", "power": 2, "kills": 2, "furnace_level": 2, "alliance_rank": 4, "kid": "1001"}])
    assert synced(configured, group_id, alliance_id, first).status == "success"
    without_count = payload(cached_at="2026-01-02T00:00:00Z", members=[{"fid": "101", "nick_name": "Northern Fox", "power": 3, "kills": 3, "furnace_level": 2, "alliance_rank": 3, "kid": "1001"}])
    del without_count["alliance"]["count"]
    assert synced(configured, group_id, alliance_id, without_count).status == "success"
    player = records.get_player(configured.database_path, group_id, "101")
    assert player is not None and player["nickname"] == "Northern Fox" and player["power"] == 3
    with sqlite3.connect(configured.database_path) as database:
        assert database.execute("SELECT roster_complete FROM alliance_stat_snapshots ORDER BY source_observed_at DESC LIMIT 1").fetchone()[0] == 0
        assert database.execute("SELECT COUNT(*) FROM player_roster_absence_observations WHERE player_fid = '102'").fetchone()[0] == 0


def test_unconfirmed_manual_profile_adopts_confirmed_roster_membership(settings: Settings) -> None:
    configured = replace(settings, whiteoutstats_api_key="test-key")
    group_id, alliance_id = setup_alliance(configured)
    records.create_player(configured.database_path, group_id, PlayerCreate(fid="101", nickname="Manual North"))
    assert synced(configured, group_id, alliance_id, payload()).status == "success"
    with sqlite3.connect(configured.database_path) as database:
        profile = database.execute("SELECT primary_alliance_id, source_type FROM player_group_profiles WHERE player_fid = '101'").fetchone()
    assert tuple(profile) == (alliance_id, "whiteoutstats")


def test_older_source_snapshot_does_not_replace_current_profile_or_membership(settings: Settings) -> None:
    configured = replace(settings, whiteoutstats_api_key="test-key")
    group_id, primary_id = setup_alliance(configured)
    academy = groups.create_additional_alliance(configured.database_path, group_id, AllianceCreate(name="Academy", tag="ACA", state_id="1001"), sync_enabled=True)
    assert academy is not None
    connect_alliance(configured, group_id, str(academy["id"]))
    newer = payload(cached_at="2026-01-02T00:00:00Z", members=[{"fid": "101", "nick_name": "New North", "power": 200, "kills": 20, "furnace_level": 31, "alliance_rank": 3, "kid": "1001"}])
    older = payload(cached_at="2026-01-01T00:00:00Z", members=[{"fid": "101", "nick_name": "Old North", "power": 100, "kills": 10, "furnace_level": 30, "alliance_rank": 4, "kid": "1001"}])
    assert synced(configured, group_id, primary_id, newer).status == "success"
    assert synced(configured, group_id, str(academy["id"]), older).status == "success"
    player = records.get_player(configured.database_path, group_id, "101")
    assert player is not None and player["nickname"] == "New North" and player["power"] == 200
    with sqlite3.connect(configured.database_path) as database:
        assert database.execute("SELECT primary_alliance_id FROM player_group_profiles WHERE player_fid = '101'").fetchone()[0] == primary_id
        assert database.execute("SELECT COUNT(*) FROM player_alliance_transitions").fetchone()[0] == 0


def test_numeric_cached_at_from_alliance_response_preserves_source_chronology(settings: Settings) -> None:
    configured = replace(settings, whiteoutstats_api_key="test-key")
    group_id, primary_id = setup_alliance(configured)
    academy = groups.create_additional_alliance(configured.database_path, group_id, AllianceCreate(name="Academy", tag="ACA", state_id="1001"), sync_enabled=True)
    assert academy is not None
    connect_alliance(configured, group_id, str(academy["id"]))
    newer = payload(
        cached_at=1_700_000_100.25,
        members=[{"fid": "101", "nick_name": "Current North", "power": 200, "kills": 20, "furnace_level": 31, "alliance_rank": 3, "kid": "1001"}],
    )
    newer["age_seconds"] = 184
    older = payload(
        cached_at=1_700_000_000.5,
        members=[{"fid": "101", "nick_name": "Old North", "power": 100, "kills": 10, "furnace_level": 30, "alliance_rank": 4, "kid": "1001"}],
    )
    older["age_seconds"] = 284

    assert synced(configured, group_id, primary_id, newer).status == "success"
    assert synced(configured, group_id, str(academy["id"]), older).status == "success"

    player = records.get_player(configured.database_path, group_id, "101")
    assert player is not None and player["nickname"] == "Current North" and player["power"] == 200
    with sqlite3.connect(configured.database_path) as database:
        assert database.execute("SELECT source_observed_at FROM alliance_stat_snapshots WHERE alliance_id = ?", (primary_id,)).fetchone()[0] == "2023-11-14T22:15:00.250000Z"
        assert database.execute("SELECT COUNT(*) FROM player_alliance_transitions").fetchone()[0] == 0


def test_missing_cached_at_does_not_write_unknown_freshness_over_existing_data(settings: Settings) -> None:
    configured = replace(settings, whiteoutstats_api_key="test-key")
    group_id, alliance_id = setup_alliance(configured)
    assert synced(configured, group_id, alliance_id, payload(members=[{"fid": "101", "nick_name": "Current North", "power": 200, "kills": 20, "furnace_level": 31, "alliance_rank": 3, "kid": "1001"}])).status == "success"
    unknown_time = payload(members=[{"fid": "101", "nick_name": "Unknown North", "power": 100, "kills": 10, "furnace_level": 30, "alliance_rank": 4, "kid": "1001"}])
    del unknown_time["cached_at"]
    unknown_time["age_seconds"] = 184

    result = synced(configured, group_id, alliance_id, unknown_time)

    assert result.status == "failed" and result.message == "WhiteoutStats response is missing cached_at"
    player = records.get_player(configured.database_path, group_id, "101")
    assert player is not None and player["nickname"] == "Current North" and player["power"] == 200
    with sqlite3.connect(configured.database_path) as database:
        assert database.execute("SELECT COUNT(*) FROM alliance_stat_snapshots").fetchone()[0] == 1
        assert database.execute("SELECT COUNT(*) FROM player_membership_observations").fetchone()[0] == 1


def test_temporary_then_permanent_transfer_after_48_hours(settings: Settings) -> None:
    configured = replace(settings, whiteoutstats_api_key="test-key")
    group_id, primary_id = setup_alliance(configured)
    additional = groups.create_additional_alliance(configured.database_path, group_id, AllianceCreate(name="Academy", tag="ACA", state_id="1001"), sync_enabled=True)
    assert additional is not None
    connect_alliance(configured, group_id, str(additional["id"]))
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


def test_return_closes_temporary_transition_before_a_later_new_departure(settings: Settings) -> None:
    configured = replace(settings, whiteoutstats_api_key="test-key")
    group_id, primary_id = setup_alliance(configured)
    academy = groups.create_additional_alliance(configured.database_path, group_id, AllianceCreate(name="Academy", tag="ACA", state_id="1001"), sync_enabled=True)
    assert academy is not None
    connect_alliance(configured, group_id, str(academy["id"]))
    academy_id = str(academy["id"])
    assert synced(configured, group_id, primary_id, payload(cached_at="2026-01-01T00:00:00Z")).status == "success"
    assert synced(configured, group_id, academy_id, payload(cached_at="2026-01-02T00:00:00Z")).status == "success"
    assert synced(configured, group_id, primary_id, payload(cached_at="2026-01-03T00:00:00Z")).status == "success"
    assert synced(configured, group_id, academy_id, payload(cached_at="2026-01-06T00:00:00Z")).status == "success"
    with sqlite3.connect(configured.database_path) as database:
        transitions = database.execute("SELECT classification, first_observed_at FROM player_alliance_transitions ORDER BY first_observed_at").fetchall()
    assert [row[0] for row in transitions] == ["disputed", "temporary_pending"]
    assert transitions[1][1] == "2026-01-06T00:00:00Z"


def test_state_change_confirms_transfer_immediately_and_groups_stay_isolated(settings: Settings) -> None:
    configured = replace(settings, whiteoutstats_api_key="test-key")
    group_id, primary_id = setup_alliance(configured)
    moved = groups.create_additional_alliance(configured.database_path, group_id, AllianceCreate(name="Moved", tag="MOV", state_id="1002"), sync_enabled=True)
    assert moved is not None
    connect_alliance(configured, group_id, str(moved["id"]))
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


def test_scheduler_uses_backoff_for_failures_and_limits_transient_followups(settings: Settings) -> None:
    configured = replace(settings, whiteoutstats_api_key="test-key")
    group_id, alliance_id = setup_alliance(configured)
    failed = whiteoutstats.sync_alliance(configured.database_path, configured, group_id, alliance_id, trigger_type="scheduled", fetcher=FakeFetcher(whiteoutstats.ProviderResponse(503, {})))
    assert failed.status == "failed" and (group_id, alliance_id) not in whiteoutstats.due_alliances(configured.database_path)
    for _ in range(3):
        with sqlite3.connect(configured.database_path) as database:
            database.execute("UPDATE alliance_sync_settings SET next_retry_at = '2000-01-01T00:00:00Z' WHERE alliance_id = ?", (alliance_id,))
        result = whiteoutstats.sync_alliance(configured.database_path, configured, group_id, alliance_id, trigger_type="scheduled", fetcher=FakeFetcher(whiteoutstats.ProviderResponse(202, {"pending": True}, 1)))
        assert result.status == "partial"
    with sqlite3.connect(configured.database_path) as database:
        attempt, retry = database.execute("SELECT last_attempt_at, next_retry_at FROM alliance_sync_settings WHERE alliance_id = ?", (alliance_id,)).fetchone()
    assert whiteoutstats._parse_timestamp(retry) >= whiteoutstats._parse_timestamp(attempt) + timedelta(minutes=719)


def test_preview_confirmation_connects_before_initial_import(settings: Settings) -> None:
    configured = replace(settings, whiteoutstats_api_key="test-key")
    database.migrate(configured.database_path)
    preview = whiteoutstats.preview_alliance(configured, "1001", "VZN", fetcher=FakeFetcher(whiteoutstats.ProviderResponse(200, payload())))
    assert preview["status"] == "success" and preview["alliance"]["aid"] == "a1"
    with sqlite3.connect(configured.database_path) as sqlite_database:
        assert sqlite_database.execute("SELECT COUNT(*) FROM players").fetchone()[0] == 0
    aid = whiteoutstats.confirmed_preview_aid(
        configured,
        str(preview["confirmation_token"]),
        state_id="1001",
        tag="VZN",
    )
    group = groups.create_group(
        configured.database_path,
        GroupCreate(name="VZN", primary_alliance_name="VZN", primary_alliance_tag="VZN", primary_alliance_state_id="1001"),
        onboarding=True,
        sync_enabled=True,
        whiteoutstats_alliance_id=aid,
    )
    alliance_id = str(groups.list_alliances(configured.database_path, str(group["id"]))[0]["id"])
    assert synced(configured, str(group["id"]), alliance_id, payload()).status == "success"
    assert records.list_players(configured.database_path, str(group["id"]), limit=10)["total"] == 1


def test_preview_rejection_or_missing_aid_does_not_connect_or_import(settings: Settings) -> None:
    configured = replace(settings, whiteoutstats_api_key="test-key")
    not_found = whiteoutstats.preview_alliance(configured, "9999", "MISSING", fetcher=FakeFetcher(whiteoutstats.ProviderResponse(404, {})))
    assert not_found == {"status": "failed", "message": "WhiteoutStats returned HTTP 404"}
    group_id, alliance_id = setup_alliance(configured)
    with sqlite3.connect(configured.database_path) as database:
        database.execute("UPDATE alliance_sync_settings SET whiteoutstats_alliance_id = NULL WHERE alliance_id = ?", (alliance_id,))
    preview = whiteoutstats.preview_alliance(configured, "1001", "VZN", fetcher=FakeFetcher(whiteoutstats.ProviderResponse(200, {"alliance": {}})))
    assert preview["status"] == "failed"
    assert synced(configured, group_id, alliance_id, payload()).message == "WhiteoutStats alliance is not connected"
    assert records.list_players(configured.database_path, group_id, limit=10)["total"] == 0


def test_existing_local_alliance_connects_after_explicit_confirmation(settings: Settings) -> None:
    configured = replace(settings, whiteoutstats_api_key="test-key")
    database.migrate(configured.database_path)
    group = groups.create_group(
        configured.database_path,
        GroupCreate(name="Local", primary_alliance_name="Local", primary_alliance_tag="LOC", primary_alliance_state_id="1001"),
        onboarding=True,
    )
    alliance_id = str(groups.list_alliances(configured.database_path, str(group["id"]))[0]["id"])
    preview = whiteoutstats.preview_alliance(configured, "1001", "LOC", fetcher=FakeFetcher(whiteoutstats.ProviderResponse(200, payload())))
    aid = whiteoutstats.confirmed_preview_aid(configured, str(preview["confirmation_token"]), state_id="1001", tag="LOC")
    connected = groups.connect_whiteoutstats_alliance(configured.database_path, str(group["id"]), alliance_id, aid, sync_enabled=True)
    assert connected is not None and connected["whiteoutstats_alliance_id"] == "a1"
    assert synced(configured, str(group["id"]), alliance_id, payload()).status == "success"


def test_identity_mismatch_never_imports_scheduled_or_manual_data(settings: Settings) -> None:
    configured = replace(settings, whiteoutstats_api_key="test-key")
    group_id, alliance_id = setup_alliance(configured)
    wrong = payload()
    wrong["alliance"]["aid"] = "other-aid"
    for trigger in ("scheduled", "manual"):
        result = whiteoutstats.sync_alliance(
            configured.database_path,
            configured,
            group_id,
            alliance_id,
            trigger_type=trigger,
            fetcher=FakeFetcher(whiteoutstats.ProviderResponse(200, wrong)),
        )
        assert result.status == "failed" and "Alliance identity mismatch: expected a1, received other-aid" in str(result.message)
    with sqlite3.connect(configured.database_path) as database:
        assert database.execute("SELECT COUNT(*) FROM player_game_stat_snapshots").fetchone()[0] == 0
        assert database.execute("SELECT COUNT(*) FROM player_membership_observations").fetchone()[0] == 0


def test_same_aid_allows_game_name_and_tag_update(settings: Settings) -> None:
    configured = replace(settings, whiteoutstats_api_key="test-key")
    group_id, alliance_id = setup_alliance(configured)
    renamed = payload()
    renamed["alliance"].update({"name": "VZN Renamed", "abbr": "VZ2"})
    assert synced(configured, group_id, alliance_id, renamed).status == "success"
    preview = whiteoutstats.preview_alliance(configured, "1001", "VZ2", fetcher=FakeFetcher(whiteoutstats.ProviderResponse(200, renamed)))
    token = str(preview["confirmation_token"])
    current = groups.get_alliance(configured.database_path, group_id, alliance_id)
    assert current is not None
    assert whiteoutstats.confirmed_preview_aid(configured, token, state_id="1001", tag="VZ2", expected_aid=str(current["whiteoutstats_alliance_id"])) == "a1"
    other = payload()
    other["alliance"]["aid"] = "other-aid"
    other_preview = whiteoutstats.preview_alliance(configured, "1001", "OTHER", fetcher=FakeFetcher(whiteoutstats.ProviderResponse(200, other)))
    with pytest.raises(ValueError, match="Alliance identity mismatch"):
        whiteoutstats.confirmed_preview_aid(configured, str(other_preview["confirmation_token"]), state_id="1001", tag="OTHER", expected_aid="a1")
    updated = groups.update_alliance(configured.database_path, group_id, alliance_id, AllianceUpdate(tag="VZ2", state_id="1001"))
    assert updated is not None and updated["tag"] == "VZ2"
    with sqlite3.connect(configured.database_path) as database:
        snapshot = database.execute("SELECT external_name, external_tag FROM alliance_stat_snapshots ORDER BY id DESC LIMIT 1").fetchone()
    assert tuple(snapshot) == ("VZN Renamed", "VZ2")


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
        preview = client.post("/api/v1/whiteoutstats/alliances/preview", headers={"X-CSRF-Token": csrf}, json={"tag": "VZN", "state_id": "1001"})
        assert preview.status_code == 200 and preview.json()["status"] == "success"
        group = client.post("/api/v1/onboarding/groups", headers={"X-CSRF-Token": csrf}, json={"name": "VZN", "primary_alliance_name": "VZN", "primary_alliance_tag": "VZN", "primary_alliance_state_id": "1001", "whiteoutstats_preview_token": preview.json()["confirmation_token"]})
        assert group.status_code == 201
        assert group.json()["initial_sync"]["status"] == "success"
        alliance_id = client.get(f"/api/v1/groups/{group.json()['id']}/alliances").json()["items"][0]["id"]
        extra_preview = client.post("/api/v1/whiteoutstats/alliances/preview", headers={"X-CSRF-Token": csrf}, json={"tag": "OTHER", "state_id": "1001"})
        extra_group = client.post("/api/v1/groups", headers={"X-CSRF-Token": csrf}, json={"name": "OTHER", "primary_alliance_name": "OTHER", "primary_alliance_tag": "OTHER", "primary_alliance_state_id": "1001", "whiteoutstats_preview_token": extra_preview.json()["confirmation_token"]})
        assert extra_group.status_code == 201 and extra_group.json()["initial_sync"]["status"] == "success"
        additional_preview = client.post("/api/v1/whiteoutstats/alliances/preview", headers={"X-CSRF-Token": csrf}, json={"tag": "ACA", "state_id": "1001"})
        additional = client.post(f"/api/v1/groups/{group.json()['id']}/alliances", headers={"X-CSRF-Token": csrf}, json={"name": "Academy", "tag": "ACA", "state_id": "1001", "whiteoutstats_preview_token": additional_preview.json()["confirmation_token"]})
        assert additional.status_code == 201 and additional.json()["initial_sync"]["status"] == "success"
        assert client.get(f"/api/v1/groups/{group.json()['id']}/alliances/{alliance_id}/sync").status_code == 200
        assert client.post(f"/api/v1/groups/{group.json()['id']}/alliances/{alliance_id}/sync").status_code == 403
        # A valid signed preview for a different AID cannot replace an existing connection.
        other_token = whiteoutstats._encode_preview_token(configured, "1001", "VZN", "other-aid")
        reassignment = client.post(
            f"/api/v1/groups/{group.json()['id']}/alliances/{alliance_id}/whiteoutstats/connect",
            headers={"X-CSRF-Token": csrf},
            json={"preview_token": other_token},
        )
        assert reassignment.status_code == 409
        assert groups.get_alliance(configured.database_path, group.json()["id"], alliance_id)["whiteoutstats_alliance_id"] == "a1"
