"""Safe, SQLite-backed WhiteoutStats roster synchronisation.

Only the free ``info,roster`` alliance endpoint is used here.  The service
stores small, typed observations instead of retaining provider JSON blobs.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from ..config import Settings
from ..database import connection, transaction


def _now() -> datetime:
    return datetime.now(UTC)


def _timestamp(value: datetime | None = None) -> str:
    return (value or _now()).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _number(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = int(value)  # provider represents some ids/ranks as strings.
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


@dataclass(frozen=True)
class ProviderResponse:
    status_code: int
    body: dict[str, Any]
    retry_after: int | None = None


class AllianceFetcher(Protocol):
    def fetch(self, state_id: str, tag: str, *, wait: int) -> ProviderResponse: ...


class AllianceInfoFetcher(Protocol):
    def fetch_info(self, state_id: str, tag: str) -> ProviderResponse: ...


class WhiteoutStatsClient:
    """Small standard-library client so production needs no extra HTTP stack."""

    def __init__(self, settings: Settings):
        self._settings = settings

    def _request(self, state_id: str, tag: str, query: dict[str, str]) -> ProviderResponse:
        if not self._settings.whiteoutstats_api_key:
            raise RuntimeError("WhiteoutStats synchronization is not configured")
        url = f"{self._settings.whiteoutstats_base_url}/alliances/{quote(state_id, safe='')}/{quote(tag, safe='')}?{urlencode(query)}"
        request = Request(url, headers={"Authorization": f"Bearer {self._settings.whiteoutstats_api_key}", "Accept": "application/json"})
        try:
            with urlopen(request, timeout=self._settings.whiteoutstats_timeout_seconds) as response:  # noqa: S310 - fixed provider base URL
                raw = response.read().decode("utf-8")
                body = json.loads(raw) if raw else {}
                retry = response.headers.get("Retry-After")
                return ProviderResponse(response.status, body if isinstance(body, dict) else {}, _number(retry))
        except HTTPError as error:
            raw = error.read().decode("utf-8", errors="replace")
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                body = {}
            return ProviderResponse(error.code, body if isinstance(body, dict) else {}, _number(error.headers.get("Retry-After")))
        except (URLError, TimeoutError, json.JSONDecodeError) as error:
            raise RuntimeError("WhiteoutStats request failed") from error

    def fetch(self, state_id: str, tag: str, *, wait: int) -> ProviderResponse:
        return self._request(state_id, tag, {"include": "info,roster", "wait": str(wait)})

    def fetch_info(self, state_id: str, tag: str) -> ProviderResponse:
        return self._request(state_id, tag, {"include": "info"})


@dataclass(frozen=True)
class SyncResult:
    status: str
    found_count: int = 0
    added_count: int = 0
    updated_count: int = 0
    message: str | None = None
    retry_after: int | None = None

    def payload(self) -> dict[str, Any]:
        return asdict(self)


def _encode_preview_token(settings: Settings, state_id: str, tag: str, aid: str) -> str:
    payload = json.dumps(
        {"state_id": state_id, "tag": tag, "aid": aid, "expires_at": int(time.time()) + 600},
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    encoded = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    signature = hmac.new(settings.session_secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def confirmed_preview_aid(
    settings: Settings,
    token: str | None,
    *,
    state_id: str,
    tag: str,
    expected_aid: str | None = None,
) -> str:
    if not token or "." not in token:
        raise ValueError("Find and confirm the WhiteoutStats alliance before saving")
    encoded, signature = token.rsplit(".", 1)
    expected_signature = hmac.new(settings.session_secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        raise ValueError("Alliance confirmation has expired or is invalid")
    try:
        raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        payload = json.loads(raw)
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError("Alliance confirmation has expired or is invalid") from error
    aid = payload.get("aid") if isinstance(payload, dict) else None
    if (
        not isinstance(aid, str)
        or not aid
        or payload.get("state_id") != state_id
        or payload.get("tag") != tag
        or not isinstance(payload.get("expires_at"), int)
        or payload["expires_at"] < int(time.time())
    ):
        raise ValueError("Alliance confirmation has expired or does not match the entered State ID and tag")
    if expected_aid is not None and aid != expected_aid:
        raise ValueError(f"Alliance identity mismatch: expected {expected_aid}, received {aid}")
    return aid


def preview_alliance(
    settings: Settings,
    state_id: str,
    tag: str,
    *,
    fetcher: AllianceInfoFetcher | None = None,
) -> dict[str, Any]:
    if not settings.whiteoutstats_api_key:
        return {"status": "not_configured", "message": "WhiteoutStats synchronization is not configured"}
    try:
        response = (fetcher or WhiteoutStatsClient(settings)).fetch_info(state_id, tag)
    except RuntimeError as error:
        return {"status": "failed", "message": str(error)}
    if response.status_code != 200:
        return {"status": "failed", "message": f"WhiteoutStats returned HTTP {response.status_code}"}
    alliance = response.body.get("alliance")
    aid = alliance.get("aid") if isinstance(alliance, dict) else None
    if not isinstance(aid, (str, int)) or not str(aid).strip():
        return {"status": "failed", "message": "WhiteoutStats did not return an Alliance ID"}
    aid_text = str(aid).strip()
    return {
        "status": "success",
        "confirmation_token": _encode_preview_token(settings, state_id, tag, aid_text),
        "alliance": {
            "aid": aid_text,
            "name": alliance.get("name") if isinstance(alliance.get("name"), str) else None,
            "tag": alliance.get("abbr") if isinstance(alliance.get("abbr"), str) else None,
            "state_id": str(alliance.get("kid")) if alliance.get("kid") is not None else None,
            "leader_name": alliance.get("leader_name") if isinstance(alliance.get("leader_name"), str) else None,
            "member_count": _number(alliance.get("count")),
            "power": _number(alliance.get("power")),
            "power_rank": _number(alliance.get("power_rank")),
            "flag_url": alliance.get("flag_url") if isinstance(alliance.get("flag_url"), str) else None,
        },
    }


def _set_terminal_result(
    database_path: str,
    alliance_id: str,
    run_id: str,
    result: SyncResult,
    *,
    retry_at: str | None = None,
) -> SyncResult:
    now = _timestamp()
    # ``alliance_sync_settings`` predates explicit rate-limit outcomes and its
    # check constraint permits success/failed/partial only.  Keep the richer
    # outcome in the immutable run record while exposing it as a retryable
    # partial attempt in the legacy settings row.
    settings_status = "partial" if result.status == "rate_limited" else result.status
    with transaction(database_path) as database:
        effective_retry_at = retry_at
        if result.status == "failed":
            # A hard error is retried on the normal cadence, not once a minute.
            effective_retry_at = _timestamp(_now() + timedelta(minutes=720))
        elif result.status in {"partial", "rate_limited"} and retry_at:
            previous_retryable_runs = int(database.execute(
                """SELECT COUNT(*) FROM alliance_sync_runs
                   WHERE alliance_id = ? AND status IN ('partial', 'rate_limited')
                     AND requested_at >= COALESCE((SELECT last_sync_at FROM alliance_sync_settings WHERE alliance_id = ?), '0000-01-01T00:00:00Z')""",
                (alliance_id, alliance_id),
            ).fetchone()[0])
            # Two follow-ups are enough to consume the provider's free refresh
            # window. Further stale/pending results return to the 12-hour cycle.
            if previous_retryable_runs >= 2:
                effective_retry_at = _timestamp(_now() + timedelta(minutes=720))
        database.execute(
            """
            UPDATE alliance_sync_settings
            SET sync_in_progress_at = NULL, next_retry_at = ?, last_sync_status = ?,
                last_sync_error = ?, last_found_count = ?, last_added_count = ?,
                last_updated_count = ?, updated_at = CURRENT_TIMESTAMP
            WHERE alliance_id = ?
            """,
            (effective_retry_at, settings_status, result.message, result.found_count, result.added_count, result.updated_count, alliance_id),
        )
        database.execute(
            """
            UPDATE alliance_sync_runs SET completed_at = ?, status = ?, found_count = ?,
              added_count = ?, updated_count = ?, message = ? WHERE id = ?
            """,
            (now, result.status, result.found_count, result.added_count, result.updated_count, result.message, run_id),
        )
    return result


def _claim_run(database_path: str, group_id: str, alliance_id: str, trigger_type: str) -> tuple[str, dict[str, Any]] | SyncResult:
    now = _now()
    now_text = _timestamp(now)
    with transaction(database_path) as database:
        alliance = database.execute(
            """
            SELECT a.id, a.group_id, a.tag, a.state_id, a.status, s.sync_enabled, s.whiteoutstats_alliance_id,
                   s.sync_in_progress_at, s.last_manual_sync_at
            FROM alliances a JOIN alliance_sync_settings s ON s.alliance_id = a.id
            WHERE a.id = ? AND a.group_id = ?
            """,
            (alliance_id, group_id),
        ).fetchone()
        if alliance is None:
            return SyncResult("failed", message="Alliance not found in selected group")
        if alliance["status"] != "active":
            return SyncResult("failed", message="Archived alliances are not synchronized")
        if not alliance["whiteoutstats_alliance_id"]:
            return SyncResult("failed", message="WhiteoutStats alliance is not connected")
        if not alliance["sync_enabled"]:
            return SyncResult("failed", message="Synchronization is disabled")
        locked_at = _parse_timestamp(alliance["sync_in_progress_at"])
        if locked_at and locked_at > now - timedelta(minutes=10):
            return SyncResult("partial", message="A synchronization is already running")
        if trigger_type == "manual":
            last_manual = _parse_timestamp(alliance["last_manual_sync_at"])
            if last_manual and last_manual > now - timedelta(minutes=5):
                return SyncResult("partial", message="Manual synchronization is limited to once every 5 minutes")
        run_id = uuid.uuid4().hex
        database.execute(
            """
            UPDATE alliance_sync_settings
            SET sync_in_progress_at = ?, last_attempt_at = ?,
                last_manual_sync_at = CASE WHEN ? = 'manual' THEN ? ELSE last_manual_sync_at END,
                next_retry_at = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE alliance_id = ?
            """,
            (now_text, now_text, trigger_type, now_text, alliance_id),
        )
        database.execute(
            """INSERT INTO alliance_sync_runs(id, alliance_id, requested_at, trigger_type, status)
               VALUES (?, ?, ?, ?, 'running')""",
            (run_id, alliance_id, now_text, trigger_type),
        )
    return run_id, dict(alliance)


def _latest_nickname(database: sqlite3.Connection, fid: str, group_id: str) -> str | None:
    row = database.execute(
        """SELECT nickname FROM player_nickname_observations
           WHERE player_fid = ? AND group_id = ? ORDER BY observed_at DESC, id DESC LIMIT 1""",
        (fid, group_id),
    ).fetchone()
    return str(row["nickname"]) if row else None


def _record_primary_history(database: sqlite3.Connection, fid: str, group_id: str, alliance_id: str, observed_at: str, transition_id: str | None = None) -> None:
    database.execute(
        """UPDATE player_primary_alliance_history SET ended_observed_at = ?
           WHERE player_fid = ? AND group_id = ? AND ended_observed_at IS NULL""",
        (observed_at, fid, group_id),
    )
    database.execute(
        """INSERT INTO player_primary_alliance_history(player_fid, group_id, alliance_id, effective_observed_at, source_type, source_transition_id)
           VALUES (?, ?, ?, ?, 'transition_rule', ?)""",
        (fid, group_id, alliance_id, observed_at, transition_id),
    )


def _apply_membership(
    database: sqlite3.Connection, *, fid: str, group_id: str, alliance_id: str, observed_at: str, state_id: str | None
) -> None:
    previous_same_source = database.execute(
        """SELECT 1 FROM player_membership_observations
           WHERE player_fid = ? AND group_id = ? AND alliance_id = ? AND source_type = 'whiteoutstats' AND source_reference = ?""",
        (fid, group_id, alliance_id, observed_at),
    ).fetchone()
    if previous_same_source:
        return
    cursor = database.execute(
        """INSERT INTO player_membership_observations(player_fid, group_id, alliance_id, observed_at, source_type, source_reference)
           VALUES (?, ?, ?, ?, 'whiteoutstats', ?)""",
        (fid, group_id, alliance_id, observed_at, observed_at),
    )
    observation_id = int(cursor.lastrowid)
    newer_observation = database.execute(
        """SELECT 1 FROM player_membership_observations
           WHERE player_fid = ? AND group_id = ? AND id <> ? AND observed_at > ? LIMIT 1""",
        (fid, group_id, observation_id, observed_at),
    ).fetchone()
    if newer_observation:
        return
    profile = database.execute(
        """SELECT primary_alliance_id, source_type FROM player_group_profiles
           WHERE player_fid = ? AND group_id = ?""",
        (fid, group_id),
    ).fetchone()
    if profile is None:
        return
    current_alliance = profile["primary_alliance_id"]
    if current_alliance is None:
        # A manual profile without an alliance is unconfirmed identity entry,
        # not a protected manual membership correction.
        database.execute(
            """UPDATE player_group_profiles SET primary_alliance_id = ?, status = 'active', source_type = 'whiteoutstats', updated_at = CURRENT_TIMESTAMP
               WHERE player_fid = ? AND group_id = ?""",
            (alliance_id, fid, group_id),
        )
        _record_primary_history(database, fid, group_id, alliance_id, observed_at)
        return
    if current_alliance == alliance_id:
        # Seeing the current alliance again interrupts any earlier tentative
        # departure. A later appearance in the destination must start fresh.
        database.execute(
            """UPDATE player_alliance_transitions
               SET classification = 'disputed', classified_at = ?, updated_at = CURRENT_TIMESTAMP
               WHERE player_fid = ? AND group_id = ? AND from_alliance_id = ?
                 AND classification = 'temporary_pending' AND first_observed_at <= ?""",
            (observed_at, fid, group_id, current_alliance, observed_at),
        )
        return
    from_state = database.execute("SELECT state_id FROM alliances WHERE id = ?", (current_alliance,)).fetchone()
    state_changed = bool(state_id and from_state and str(from_state["state_id"]) != state_id)
    pending = database.execute(
        """SELECT id, first_observed_at FROM player_alliance_transitions
           WHERE player_fid = ? AND group_id = ? AND from_alliance_id = ? AND to_alliance_id = ?
             AND classification = 'temporary_pending' ORDER BY first_observed_at DESC LIMIT 1""",
        (fid, group_id, current_alliance, alliance_id),
    ).fetchone()
    transition_id = str(pending["id"]) if pending else uuid.uuid4().hex
    first_seen = str(pending["first_observed_at"]) if pending else observed_at
    permanent = state_changed or (_parse_timestamp(observed_at) or _now()) - (_parse_timestamp(first_seen) or _now()) > timedelta(hours=48)
    if pending is None:
        database.execute(
            """INSERT INTO player_alliance_transitions(id, player_fid, group_id, from_alliance_id, to_alliance_id, first_observed_at, classification, source_observation_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (transition_id, fid, group_id, current_alliance, alliance_id, first_seen, "permanent" if permanent else "temporary_pending", observation_id),
        )
    elif permanent:
        database.execute(
            """UPDATE player_alliance_transitions SET classification = 'permanent', classified_at = ?, source_observation_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?""",
            (observed_at, observation_id, transition_id),
        )
    if permanent and profile["source_type"] != "manual":
        database.execute(
            """UPDATE player_group_profiles SET primary_alliance_id = ?, source_type = 'transition_rule', status = 'active', updated_at = CURRENT_TIMESTAMP
               WHERE player_fid = ? AND group_id = ?""",
            (alliance_id, fid, group_id),
        )
        _record_primary_history(database, fid, group_id, alliance_id, observed_at, transition_id)


def _validate_roster(body: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], bool]:
    alliance = body.get("alliance")
    members = body.get("members")
    if not isinstance(alliance, dict) or not isinstance(members, list):
        raise ValueError("WhiteoutStats returned an incomplete alliance roster")
    seen: set[str] = set()
    valid: list[dict[str, Any]] = []
    for member in members:
        if not isinstance(member, dict):
            raise ValueError("WhiteoutStats returned an invalid roster member")
        fid = member.get("fid") or member.get("chief_id")
        nickname = member.get("nick_name")
        if not isinstance(fid, (str, int)) or not str(fid).strip() or not isinstance(nickname, str) or not nickname.strip():
            raise ValueError("WhiteoutStats roster is missing a FID or nickname")
        member = dict(member)
        member["fid"] = str(fid).strip()
        member["nick_name"] = " ".join(nickname.split())
        if member["fid"] in seen:
            raise ValueError("WhiteoutStats roster contains duplicate FIDs")
        seen.add(member["fid"])
        valid.append(member)
    expected_count = _number(alliance.get("count"))
    if expected_count and not valid:
        raise ValueError("WhiteoutStats returned an empty incomplete roster")
    # Info and roster sections can be refreshed independently by the provider.
    # A count mismatch therefore makes absences unknowable, not members invalid.
    roster_complete = expected_count is not None and expected_count == len(valid)
    return alliance, valid, roster_complete


def _save_fresh_roster(database_path: str, group_id: str, alliance_id: str, run_id: str, response: dict[str, Any]) -> SyncResult:
    alliance_data, members, roster_complete = _validate_roster(response)
    observed_at = response.get("cached_at")
    if not isinstance(observed_at, str) or _parse_timestamp(observed_at) is None:
        raise ValueError("WhiteoutStats response is missing cached_at")
    received_at = _timestamp()
    added = 0
    updated = 0
    with transaction(database_path) as database:
        alliance = database.execute(
            """SELECT a.id, a.group_id, a.state_id, a.status, s.whiteoutstats_alliance_id
               FROM alliances a JOIN alliance_sync_settings s ON s.alliance_id = a.id
               WHERE a.id = ? AND a.group_id = ?""",
            (alliance_id, group_id),
        ).fetchone()
        if alliance is None or alliance["status"] != "active":
            raise ValueError("Alliance is unavailable for synchronization")
        expected_aid = alliance["whiteoutstats_alliance_id"]
        received_aid = alliance_data.get("aid")
        if not expected_aid or received_aid is None or str(received_aid) != str(expected_aid):
            received = str(received_aid) if received_aid is not None else "missing"
            raise ValueError(f"Alliance identity mismatch: expected {expected_aid or 'missing'}, received {received}")
        database.execute(
            """INSERT INTO alliance_stat_snapshots(
                alliance_id, group_id, external_aid, external_name, external_tag, state_id, power, member_count,
                power_rank, leader_name, leader_fid, flag_url, source_observed_at, received_at, roster_complete
              ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
              ON CONFLICT(alliance_id, source_observed_at) DO UPDATE
                SET roster_complete = MAX(alliance_stat_snapshots.roster_complete, excluded.roster_complete)""",
            (
                alliance_id, group_id, str(alliance_data.get("aid")) if alliance_data.get("aid") is not None else None,
                alliance_data.get("name") if isinstance(alliance_data.get("name"), str) else None,
                alliance_data.get("abbr") if isinstance(alliance_data.get("abbr"), str) else None,
                str(alliance_data.get("kid")) if alliance_data.get("kid") is not None else None,
                _number(alliance_data.get("power")), _number(alliance_data.get("count")), _number(alliance_data.get("power_rank")),
                alliance_data.get("leader_name") if isinstance(alliance_data.get("leader_name"), str) else None,
                str(alliance_data.get("leader_chief_id")) if alliance_data.get("leader_chief_id") is not None else None,
                alliance_data.get("flag_url") if isinstance(alliance_data.get("flag_url"), str) else None,
                observed_at, received_at, int(roster_complete),
            ),
        )
        snapshot_row = database.execute(
            "SELECT id FROM alliance_stat_snapshots WHERE alliance_id = ? AND source_observed_at = ?",
            (alliance_id, observed_at),
        ).fetchone()
        if snapshot_row is None:
            raise RuntimeError("Alliance snapshot was not persisted")
        snapshot_id = int(snapshot_row["id"])
        previous_snapshot = database.execute(
            """SELECT id FROM alliance_stat_snapshots
               WHERE alliance_id = ? AND roster_complete = 1 AND source_observed_at < ?
               ORDER BY source_observed_at DESC, id DESC LIMIT 1""",
            (alliance_id, observed_at),
        ).fetchone()
        member_fids = {str(member["fid"]) for member in members}
        if roster_complete and previous_snapshot:
            previous_members = database.execute(
                "SELECT player_fid FROM alliance_roster_snapshot_members WHERE alliance_snapshot_id = ?",
                (previous_snapshot["id"],),
            ).fetchall()
            for previous_member in previous_members:
                fid = str(previous_member["player_fid"])
                if fid not in member_fids:
                    database.execute(
                        """INSERT OR IGNORE INTO player_roster_absence_observations(player_fid, group_id, alliance_id, alliance_snapshot_id, observed_at)
                           VALUES (?, ?, ?, ?, ?)""",
                        (fid, group_id, alliance_id, snapshot_id, observed_at),
                    )
        for member in members:
            fid = member["fid"]
            exists = database.execute("SELECT 1 FROM players WHERE fid = ?", (fid,)).fetchone()
            if not exists:
                database.execute("INSERT INTO players(fid, nickname) VALUES (?, ?)", (fid, member["nick_name"]))
                database.execute("INSERT INTO player_nicknames(player_fid, nickname) VALUES (?, ?)", (fid, member["nick_name"]))
            profile = database.execute(
                "SELECT 1 FROM player_group_profiles WHERE player_fid = ? AND group_id = ?", (fid, group_id)
            ).fetchone()
            if profile is None:
                database.execute(
                    """INSERT INTO player_group_profiles(player_fid, group_id, primary_alliance_id, status, source_type)
                       VALUES (?, ?, ?, 'active', 'whiteoutstats')""",
                    (fid, group_id, alliance_id),
                )
                _record_primary_history(database, fid, group_id, alliance_id, observed_at)
                added += 1
            current_nickname = _latest_nickname(database, fid, group_id)
            if current_nickname != member["nick_name"]:
                database.execute(
                    """INSERT INTO player_nickname_observations(player_fid, group_id, alliance_id, nickname, observed_at, source_type, source_reference)
                       VALUES (?, ?, ?, ?, ?, 'whiteoutstats', ?)""",
                    (fid, group_id, alliance_id, member["nick_name"], observed_at, observed_at),
                )
            existing_stats = database.execute(
                "SELECT power, kills, furnace_level, alliance_rank, state_id, observed_at FROM player_whiteoutstats_profiles WHERE player_fid = ? AND group_id = ?",
                (fid, group_id),
            ).fetchone()
            values = (_number(member.get("power")), _number(member.get("kills")), _number(member.get("furnace_level")),
                      str(member.get("alliance_rank")) if member.get("alliance_rank") is not None else None,
                      str(member.get("kid")) if member.get("kid") is not None else None)
            current_stats = existing_stats is None or (_parse_timestamp(observed_at) or _now()) > (_parse_timestamp(existing_stats["observed_at"]) or _now())
            if current_stats and existing_stats and tuple(existing_stats[:5]) != values:
                updated += 1
            elif current_stats and profile is not None:
                updated += 1
            if current_stats:
                database.execute(
                    """INSERT INTO player_whiteoutstats_profiles(player_fid, group_id, uid, power, kills, furnace_level, alliance_rank, state_id, avatar_url, observed_at, received_at, source_alliance_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(player_fid, group_id) DO UPDATE SET uid=excluded.uid, power=excluded.power, kills=excluded.kills,
                         furnace_level=excluded.furnace_level, alliance_rank=excluded.alliance_rank, state_id=excluded.state_id,
                         avatar_url=excluded.avatar_url, observed_at=excluded.observed_at, received_at=excluded.received_at, source_alliance_id=excluded.source_alliance_id""",
                    (fid, group_id, str(member.get("uid")) if member.get("uid") is not None else None, *values,
                     member.get("avatar_url") if isinstance(member.get("avatar_url"), str) else None, observed_at, received_at, alliance_id),
                )
            database.execute(
                """INSERT OR IGNORE INTO player_game_stat_snapshots(player_fid, group_id, alliance_id, uid, power, kills, furnace_level, alliance_rank, state_id, source_observed_at, received_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (fid, group_id, alliance_id, str(member.get("uid")) if member.get("uid") is not None else None, *values, observed_at, received_at),
            )
            database.execute(
                "INSERT OR IGNORE INTO alliance_roster_snapshot_members(alliance_snapshot_id, player_fid) VALUES (?, ?)",
                (snapshot_id, fid),
            )
            _apply_membership(database, fid=fid, group_id=group_id, alliance_id=alliance_id, observed_at=observed_at, state_id=values[4])
        result = SyncResult("success", len(members), added, updated)
        database.execute(
            """UPDATE alliance_sync_settings SET sync_in_progress_at = NULL, next_retry_at = NULL, last_sync_at = ?, last_sync_status = 'success',
              last_sync_error = NULL, last_found_count = ?, last_added_count = ?, last_updated_count = ?, updated_at = CURRENT_TIMESTAMP WHERE alliance_id = ?""",
            (received_at, result.found_count, result.added_count, result.updated_count, alliance_id),
        )
        database.execute(
            """UPDATE alliance_sync_runs SET completed_at = ?, status = 'success', found_count = ?, added_count = ?, updated_count = ? WHERE id = ?""",
            (received_at, result.found_count, result.added_count, result.updated_count, run_id),
        )
    return result


def sync_alliance(
    database_path: str, settings: Settings, group_id: str, alliance_id: str, *, trigger_type: str, fetcher: AllianceFetcher | None = None
) -> SyncResult:
    if not settings.whiteoutstats_api_key:
        return SyncResult("failed", message="Synchronization is not configured")
    claimed = _claim_run(database_path, group_id, alliance_id, trigger_type)
    if isinstance(claimed, SyncResult):
        return claimed
    run_id, alliance = claimed
    provider = fetcher or WhiteoutStatsClient(settings)
    try:
        response = provider.fetch(str(alliance["state_id"]), str(alliance["tag"]), wait=30)
        # A very short, provider-approved follow-up is free and avoids making the
        # browser wait indefinitely for a queue that takes longer than expected.
        if response.status_code == 200 and response.body.get("fresh") is False and response.retry_after and response.retry_after <= 3:
            time.sleep(response.retry_after)
            response = provider.fetch(str(alliance["state_id"]), str(alliance["tag"]), wait=0)
        retry_after = response.retry_after or _number(response.body.get("retry_after"))
        if response.status_code == 429:
            retry_at = _timestamp(_now() + timedelta(seconds=retry_after or 60))
            return _set_terminal_result(database_path, alliance_id, run_id, SyncResult("rate_limited", message="WhiteoutStats rate limit reached", retry_after=retry_after), retry_at=retry_at)
        if response.status_code == 202 or response.body.get("pending"):
            retry_at = _timestamp(_now() + timedelta(seconds=retry_after or 60))
            return _set_terminal_result(database_path, alliance_id, run_id, SyncResult("partial", message="WhiteoutStats is still preparing the roster", retry_after=retry_after), retry_at=retry_at)
        if response.status_code != 200:
            return _set_terminal_result(database_path, alliance_id, run_id, SyncResult("failed", message=f"WhiteoutStats returned HTTP {response.status_code}"))
        provider_alliance = response.body.get("alliance")
        received_aid = provider_alliance.get("aid") if isinstance(provider_alliance, dict) else None
        expected_aid = alliance["whiteoutstats_alliance_id"]
        if received_aid is None or str(received_aid) != str(expected_aid):
            received = str(received_aid) if received_aid is not None else "missing"
            return _set_terminal_result(
                database_path,
                alliance_id,
                run_id,
                SyncResult("failed", message=f"Alliance identity mismatch: expected {expected_aid}, received {received}"),
            )
        if response.body.get("fresh") is not True:
            retry_at = _timestamp(_now() + timedelta(seconds=retry_after or 60))
            return _set_terminal_result(database_path, alliance_id, run_id, SyncResult("partial", message="WhiteoutStats returned cached roster; refresh is pending", retry_after=retry_after), retry_at=retry_at)
        return _save_fresh_roster(database_path, group_id, alliance_id, run_id, response.body)
    except (RuntimeError, ValueError, sqlite3.Error) as error:
        return _set_terminal_result(database_path, alliance_id, run_id, SyncResult("failed", message=str(error)))


def sync_status(database_path: str, group_id: str, alliance_id: str, *, configured: bool) -> dict[str, Any] | None:
    with connection(database_path) as database:
        row = database.execute(
            """SELECT s.sync_enabled, s.sync_interval_minutes, s.last_sync_at, s.last_attempt_at, s.last_sync_status,
                      s.last_sync_error, s.sync_in_progress_at, s.next_retry_at, s.last_found_count, s.last_added_count, s.last_updated_count,
                      a.state_id, a.tag, a.status, s.whiteoutstats_alliance_id
               FROM alliance_sync_settings s JOIN alliances a ON a.id = s.alliance_id
               WHERE a.id = ? AND a.group_id = ?""",
            (alliance_id, group_id),
        ).fetchone()
        if row is None:
            return None
        runs = database.execute(
            """SELECT requested_at, completed_at, trigger_type, status, found_count, added_count, updated_count, message
               FROM alliance_sync_runs WHERE alliance_id = ? ORDER BY requested_at DESC LIMIT 5""", (alliance_id,)
        ).fetchall()
    result = dict(row)
    result["api_configured"] = configured
    result["runs"] = [dict(item) for item in runs]
    return result


def update_sync_settings(database_path: str, group_id: str, alliance_id: str, *, enabled: bool, configured: bool) -> dict[str, Any] | None:
    if enabled and not configured:
        raise ValueError("WhiteoutStats API key is not configured on the backend")
    with transaction(database_path) as database:
        row = database.execute(
            """SELECT a.status, s.whiteoutstats_alliance_id FROM alliances a
               JOIN alliance_sync_settings s ON s.alliance_id = a.id
               WHERE a.id = ? AND a.group_id = ?""",
            (alliance_id, group_id),
        ).fetchone()
        if row is None:
            return None
        if row["status"] != "active" and enabled:
            raise ValueError("Archived alliances cannot be synchronized")
        if enabled and not row["whiteoutstats_alliance_id"]:
            raise ValueError("Connect and confirm the WhiteoutStats alliance before enabling synchronization")
        database.execute("UPDATE alliance_sync_settings SET sync_enabled = ?, sync_interval_minutes = 720, updated_at = CURRENT_TIMESTAMP WHERE alliance_id = ?", (int(enabled), alliance_id))
    return sync_status(database_path, group_id, alliance_id, configured=configured)


def due_alliances(database_path: str) -> list[tuple[str, str]]:
    now = _now()
    due: list[tuple[str, str]] = []
    with connection(database_path) as database:
        rows = database.execute(
            """SELECT a.group_id, a.id, s.last_sync_at, s.last_attempt_at, s.next_retry_at, s.sync_in_progress_at
               FROM alliances a JOIN alliance_sync_settings s ON s.alliance_id = a.id
               JOIN alliance_groups g ON g.id = a.group_id
               WHERE a.status = 'active' AND g.status = 'active' AND s.sync_enabled = 1
                 AND s.whiteoutstats_alliance_id IS NOT NULL"""
        ).fetchall()
    for row in rows:
        lock = _parse_timestamp(row["sync_in_progress_at"])
        if lock and lock > now - timedelta(minutes=10):
            continue
        retry = _parse_timestamp(row["next_retry_at"])
        if retry and retry > now:
            continue
        last_sync = _parse_timestamp(row["last_sync_at"])
        last_attempt = _parse_timestamp(row["last_attempt_at"])
        if retry is None and last_attempt and (last_sync is None or last_attempt > last_sync) and last_attempt > now - timedelta(minutes=720):
            continue
        if last_sync is None or last_sync <= now - timedelta(minutes=720):
            due.append((str(row["group_id"]), str(row["id"])))
    return due


class WhiteoutStatsScheduler:
    def __init__(self, database_path: str, settings: Settings):
        self._database_path = database_path
        self._settings = settings
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if not self._settings.whiteoutstats_api_key:
            return
        self._task = asyncio.create_task(self._run(), name="whiteoutstats-scheduler")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        while True:
            for group_id, alliance_id in due_alliances(self._database_path):
                await asyncio.to_thread(sync_alliance, self._database_path, self._settings, group_id, alliance_id, trigger_type="scheduled")
            await asyncio.sleep(60)
