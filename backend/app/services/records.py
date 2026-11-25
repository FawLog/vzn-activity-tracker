"""Explicit, group-scoped data-access operations for roster, events, and audit records."""

from __future__ import annotations

import sqlite3
import uuid
from typing import Any

from ..database import connection, transaction
from ..schemas import EventCreate, PlayerCreate

PLAYER_SORT_COLUMNS = {
    "fid": "pgp.player_fid",
    "nickname": "pno.nickname",
    "created_at": "pgp.created_at",
    "power": "wsp.power",
    "kills": "wsp.kills",
    "furnace_level": "wsp.furnace_level",
    "alliance_rank": "CASE UPPER(TRIM(wsp.alliance_rank)) "
    "WHEN '1' THEN 1 WHEN 'R1' THEN 1 WHEN '2' THEN 2 WHEN 'R2' THEN 2 "
    "WHEN '3' THEN 3 WHEN 'R3' THEN 3 WHEN '4' THEN 4 WHEN 'R4' THEN 4 "
    "WHEN '5' THEN 5 WHEN 'R5' THEN 5 END",
}
EVENT_SORT_COLUMNS = {"occurred_on": "e.occurred_on", "event_type": "e.event_type", "status": "e.status"}


def _group_exists(database: sqlite3.Connection, group_id: str) -> bool:
    return bool(database.execute("SELECT 1 FROM alliance_groups WHERE id = ?", (group_id,)).fetchone())


def _group_status(database: sqlite3.Connection, group_id: str) -> str | None:
    row = database.execute("SELECT status FROM alliance_groups WHERE id = ?", (group_id,)).fetchone()
    return str(row["status"]) if row else None


def _alliance_in_group(database: sqlite3.Connection, group_id: str, alliance_id: str) -> bool:
    return bool(
        database.execute(
            "SELECT 1 FROM alliances WHERE id = ? AND group_id = ?", (alliance_id, group_id)
        ).fetchone()
    )


def overview(database_path: str, group_id: str, alliance_id: str | None = None) -> dict[str, Any] | None:
    with connection(database_path) as database:
        if not _group_exists(database, group_id):
            return None
        selected_alliance = alliance_id
        if selected_alliance and not _alliance_in_group(database, group_id, selected_alliance):
            raise ValueError("Alliance does not belong to this group")
        if selected_alliance is None:
            primary = database.execute(
                "SELECT id FROM alliances WHERE group_id = ? AND alliance_type = 'primary'", (group_id,)
            ).fetchone()
            selected_alliance = str(primary["id"]) if primary else None
        players = database.execute(
            "SELECT COUNT(*) FROM player_group_profiles WHERE group_id = ?", (group_id,)
        ).fetchone()[0]
        events = database.execute(
            """
            SELECT COUNT(*) FROM events e JOIN alliances a ON a.id = e.alliance_id
            WHERE a.group_id = ?
            """,
            (group_id,),
        ).fetchone()[0]
        published = database.execute(
            """
            SELECT COUNT(*) FROM events e JOIN alliances a ON a.id = e.alliance_id
            WHERE a.group_id = ? AND e.status = 'published'
            """,
            (group_id,),
        ).fetchone()[0]
        recent = database.execute(
            """
            SELECT e.id, e.alliance_id, a.name AS alliance_name, e.event_type, e.occurred_on,
                   e.status, e.created_at, e.updated_at, (SELECT COUNT(*) FROM (SELECT player_fid FROM event_participants WHERE event_id=e.id UNION SELECT r.player_fid FROM event_session_roster r JOIN event_sessions s ON s.id=r.session_id WHERE s.event_id=e.id)) AS participant_count
            FROM events e
            JOIN alliances a ON a.id = e.alliance_id
            LEFT JOIN event_participants ep ON ep.event_id = e.id
            WHERE a.group_id = ?
            GROUP BY e.id
            ORDER BY e.occurred_on DESC, e.created_at DESC
            LIMIT 5
            """,
            (group_id,),
        ).fetchall()
        snapshot = None
        previous_snapshot = None
        if selected_alliance:
            snapshot = database.execute(
                """SELECT external_name, external_tag, state_id, power, member_count, power_rank, leader_name,
                          flag_url, source_observed_at, received_at
                   FROM alliance_stat_snapshots WHERE alliance_id = ?
                   ORDER BY source_observed_at DESC, id DESC LIMIT 1""",
                (selected_alliance,),
            ).fetchone()
            previous_snapshot = database.execute(
                """SELECT power FROM alliance_stat_snapshots WHERE alliance_id = ?
                   ORDER BY source_observed_at DESC, id DESC LIMIT 1 OFFSET 1""",
                (selected_alliance,),
            ).fetchone()
    alliance_stats = dict(snapshot) if snapshot else None
    if alliance_stats:
        alliance_stats["power_change"] = (alliance_stats["power"] - previous_snapshot["power"]
                                          if previous_snapshot and alliance_stats["power"] is not None and previous_snapshot["power"] is not None else None)
    return {"players": players, "events": events, "published_events": published, "recent_events": [dict(row) for row in recent], "alliance": alliance_stats}


def list_players(
    database_path: str,
    group_id: str,
    *,
    alliance_id: str | None = None,
    affiliation: str | None = None,
    query: str = "",
    sort: str = "nickname",
    direction: str = "asc",
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any] | None:
    sort_column = PLAYER_SORT_COLUMNS.get(sort, "pno.nickname")
    sort_direction = "DESC" if direction == "desc" else "ASC"
    pattern = f"%{query.strip()}%"
    filter_mode = affiliation or ("alliance" if alliance_id else "all")
    if filter_mode not in {"all", "alliance", "unconfirmed"}:
        raise ValueError("Unknown player affiliation filter")
    with connection(database_path) as database:
        if not _group_exists(database, group_id):
            return None
        if filter_mode == "alliance" and not alliance_id:
            raise ValueError("Alliance filter requires an alliance")
        if filter_mode == "alliance" and not _alliance_in_group(database, group_id, alliance_id):
            raise ValueError("Alliance does not belong to this group")
        affiliation_condition = {
            "all": "1 = 1",
            "alliance": "pgp.primary_alliance_id = ?",
            "unconfirmed": "pgp.primary_alliance_id IS NULL",
        }[filter_mode]
        parameters: list[str | None] = [group_id]
        if filter_mode == "alliance":
            parameters.append(alliance_id)
        parameters.extend([query.strip(), pattern, pattern])
        total = database.execute(
            f"""SELECT COUNT(*) FROM player_group_profiles pgp
            LEFT JOIN player_nickname_observations pno ON pno.id = (
                SELECT observation.id FROM player_nickname_observations observation
                WHERE observation.player_fid = pgp.player_fid AND observation.group_id = pgp.group_id
                ORDER BY observation.observed_at DESC, observation.id DESC LIMIT 1)
            WHERE pgp.group_id = ? AND {affiliation_condition}
              AND (? = '' OR pgp.player_fid LIKE ? OR pno.nickname LIKE ?)""",
            parameters,
        ).fetchone()[0]
        rows = database.execute(
            f"""
            SELECT pgp.player_fid AS fid, pno.nickname, pgp.created_at, pgp.updated_at,
                   pgp.status AS group_status, pgp.primary_alliance_id,
                   primary_alliance.name AS primary_alliance_name,
                   wsp.power, wsp.kills, wsp.furnace_level, wsp.alliance_rank, wsp.state_id, wsp.avatar_url,
                   source_alliance.name AS observed_alliance_name
            FROM player_group_profiles pgp
            LEFT JOIN alliances primary_alliance
              ON primary_alliance.id = pgp.primary_alliance_id
             AND primary_alliance.group_id = pgp.group_id
            LEFT JOIN player_nickname_observations pno ON pno.id = (
                SELECT observation.id
                FROM player_nickname_observations observation
                WHERE observation.player_fid = pgp.player_fid
                  AND observation.group_id = pgp.group_id
                ORDER BY observation.observed_at DESC, observation.id DESC
                LIMIT 1
            )
            LEFT JOIN player_whiteoutstats_profiles wsp
              ON wsp.player_fid = pgp.player_fid AND wsp.group_id = pgp.group_id
            LEFT JOIN alliances source_alliance ON source_alliance.id = wsp.source_alliance_id
            WHERE pgp.group_id = ?
              AND {affiliation_condition}
              AND (? = '' OR pgp.player_fid LIKE ? OR pno.nickname LIKE ?)
            ORDER BY {sort_column} {sort_direction} NULLS LAST, pgp.player_fid ASC
            LIMIT ? OFFSET ?
            """,
            (*parameters, limit, offset),
        ).fetchall()
    items: list[dict[str, Any]] = []
    external_fields = {"power", "kills", "furnace_level", "alliance_rank", "state_id", "observed_alliance_name", "avatar_url"}
    for row in rows:
        item = dict(row)
        for field in external_fields:
            if item[field] is None:
                item.pop(field)
        items.append(item)
    return {"items": items, "total": int(total), "limit": limit, "offset": offset}


def get_player(database_path: str, group_id: str, fid: str) -> dict[str, Any] | None:
    with connection(database_path) as database:
        profile = database.execute(
            """
            SELECT pgp.player_fid AS fid, pno.nickname, pgp.created_at, pgp.updated_at, pgp.status AS group_status,
                   pgp.primary_alliance_id, a.name AS primary_alliance_name,
                   wsp.uid, wsp.power, wsp.kills, wsp.furnace_level, wsp.alliance_rank, wsp.state_id,
                   wsp.avatar_url, wsp.observed_at AS stats_observed_at, observed.name AS observed_alliance_name
            FROM player_group_profiles pgp
            LEFT JOIN alliances a ON a.id = pgp.primary_alliance_id AND a.group_id = pgp.group_id
            LEFT JOIN player_nickname_observations pno ON pno.id = (
                SELECT observation.id
                FROM player_nickname_observations observation
                WHERE observation.player_fid = pgp.player_fid
                  AND observation.group_id = pgp.group_id
                ORDER BY observation.observed_at DESC, observation.id DESC
                LIMIT 1
            )
            LEFT JOIN player_whiteoutstats_profiles wsp ON wsp.player_fid = pgp.player_fid AND wsp.group_id = pgp.group_id
            LEFT JOIN alliances observed ON observed.id = wsp.source_alliance_id
            WHERE pgp.group_id = ? AND pgp.player_fid = ?
            """,
            (group_id, fid),
        ).fetchone()
        if profile is None:
            return None
        nicknames = database.execute(
            """
            SELECT nickname, observed_at AS valid_from, NULL AS valid_to
            FROM player_nickname_observations
            WHERE player_fid = ? AND group_id = ?
            ORDER BY observed_at DESC, id DESC
            """,
            (fid, group_id),
        ).fetchall()
        statistics = database.execute(
            """SELECT power, kills, furnace_level, alliance_rank, state_id, source_observed_at, received_at, alliance_id
               FROM player_game_stat_snapshots WHERE player_fid = ? AND group_id = ?
               ORDER BY source_observed_at DESC, id DESC LIMIT 90""",
            (fid, group_id),
        ).fetchall()
        memberships = database.execute(
            """SELECT mo.observed_at, mo.confidence, a.name AS alliance_name, a.tag AS alliance_tag
               FROM player_membership_observations mo JOIN alliances a ON a.id = mo.alliance_id
               WHERE mo.player_fid = ? AND mo.group_id = ? ORDER BY mo.observed_at DESC, mo.id DESC LIMIT 90""",
            (fid, group_id),
        ).fetchall()
    result = dict(profile)
    result["nickname_history"] = [dict(row) for row in nicknames]
    result["stat_history"] = [dict(row) for row in statistics]
    result["membership_history"] = [dict(row) for row in memberships]
    return result


def create_player(database_path: str, group_id: str, payload: PlayerCreate) -> dict[str, Any]:
    try:
        with transaction(database_path) as database:
            group_status = _group_status(database, group_id)
            if group_status is None:
                raise LookupError("Group not found")
            if group_status != "active":
                raise ValueError("Cannot add a player to an archived group")
            existing = database.execute("SELECT 1 FROM players WHERE fid = ?", (payload.fid,)).fetchone()
            if existing is None:
                database.execute("INSERT INTO players(fid, nickname) VALUES (?, ?)", (payload.fid, payload.nickname))
                database.execute(
                    "INSERT INTO player_nicknames(player_fid, nickname) VALUES (?, ?)",
                    (payload.fid, payload.nickname),
                )
            database.execute(
                """
                INSERT INTO player_group_profiles(player_fid, group_id, status, source_type)
                VALUES (?, ?, 'unconfirmed', 'manual')
                """,
                (payload.fid, group_id),
            )
            database.execute(
                """
                INSERT INTO player_nickname_observations(player_fid, group_id, nickname, observed_at, source_type)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP, 'manual')
                """,
                (payload.fid, group_id, payload.nickname),
            )
            database.execute(
                """
                INSERT INTO audit_log(action, entity_type, entity_id, actor)
                VALUES ('created', 'player_group_profile', ?, 'admin')
                """,
                (f"{group_id}:{payload.fid}",),
            )
    except sqlite3.IntegrityError as error:
        raise ValueError("This player already belongs to the selected group") from error
    player = get_player(database_path, group_id, payload.fid)
    if player is None:
        raise RuntimeError("Player profile was not persisted")
    return player


def list_events(
    database_path: str,
    group_id: str,
    alliance_id: str,
    *,
    sort: str = "occurred_on",
    direction: str = "desc",
) -> list[dict[str, Any]] | None:
    sort_column = EVENT_SORT_COLUMNS.get(sort, "e.occurred_on")
    sort_direction = "ASC" if direction == "asc" else "DESC"
    with connection(database_path) as database:
        if not _alliance_in_group(database, group_id, alliance_id):
            return None
        rows = database.execute(
            f"""
            SELECT e.id, e.alliance_id, e.event_type, e.occurred_on, e.status,
                   e.created_at, e.updated_at, (SELECT COUNT(*) FROM (SELECT player_fid FROM event_participants WHERE event_id=e.id UNION SELECT r.player_fid FROM event_session_roster r JOIN event_sessions s ON s.id=r.session_id WHERE s.event_id=e.id)) AS participant_count
            FROM events e LEFT JOIN event_participants ep ON ep.event_id = e.id
            WHERE e.alliance_id = ?
            GROUP BY e.id
            ORDER BY {sort_column} {sort_direction}, e.created_at DESC
            LIMIT 100
            """,
            (alliance_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_event(database_path: str, group_id: str, event_id: str) -> dict[str, Any] | None:
    with connection(database_path) as database:
        event = database.execute(
            """
            SELECT e.id, e.alliance_id, a.name AS alliance_name, e.event_type, e.occurred_on,
                   e.status, e.created_at, e.updated_at
            FROM events e JOIN alliances a ON a.id = e.alliance_id
            WHERE e.id = ? AND a.group_id = ?
            """,
            (event_id, group_id),
        ).fetchone()
        if event is None:
            return None
        participants = database.execute(
            """
            SELECT ep.player_fid AS fid,
                   COALESCE((
                       SELECT observation.nickname
                       FROM player_nickname_observations observation
                       WHERE observation.player_fid = ep.player_fid
                         AND observation.group_id = ?
                       ORDER BY observation.observed_at DESC, observation.id DESC
                       LIMIT 1
                   ), 'Nickname unconfirmed') AS nickname,
                   ep.presence_status, ep.roster_role,
                   ep.raw_points, ep.source_complete
            FROM event_participants ep
            WHERE ep.event_id = ? ORDER BY nickname COLLATE NOCASE, ep.player_fid ASC
            """,
            (group_id, event_id),
        ).fetchall()
    result = dict(event)
    result["participants"] = [dict(row) for row in participants]
    return result


def create_event(database_path: str, group_id: str, alliance_id: str, payload: EventCreate) -> dict[str, Any]:
    if payload.event_type.value in {"alliance_mobilization", "alliance_championship", "foundry", "canyon", "bear_trap"} and payload.status.value != "draft":
        raise ValueError("Create a draft and publish reviewed results through the editor")
    event_id = uuid.uuid4().hex
    with transaction(database_path) as database:
        group_status = _group_status(database, group_id)
        if group_status is None:
            raise LookupError("Group not found")
        if group_status != "active":
            raise ValueError("Cannot create an event in an archived group")
        alliance = database.execute(
            "SELECT status FROM alliances WHERE id = ? AND group_id = ?",
            (alliance_id, group_id),
        ).fetchone()
        if alliance is None:
            raise LookupError("Alliance not found in selected group")
        if alliance["status"] != "active":
            raise ValueError("Cannot create an event in an archived alliance")
        database.execute(
            """
            INSERT INTO events(id, alliance_id, event_type, occurred_on, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (event_id, alliance_id, payload.event_type.value, payload.occurred_on.isoformat(), payload.status.value),
        )
        if payload.event_type.value in {"alliance_mobilization", "alliance_championship"}:
            database.execute("INSERT INTO event_sessions(id,event_id,session_key,started_at) VALUES (?,?,?,?)",
                             (uuid.uuid4().hex,event_id,"main",payload.occurred_on.isoformat()+"T00:00:00+00:00"))
        database.execute(
            """
            INSERT INTO audit_log(action, entity_type, entity_id, actor)
            VALUES ('created', 'event', ?, 'admin')
            """,
            (event_id,),
        )
    event = get_event(database_path, group_id, event_id)
    if event is None:
        raise RuntimeError("Event was not persisted")
    return event


def list_audit(database_path: str) -> list[dict[str, Any]]:
    with connection(database_path) as database:
        rows = database.execute(
            """SELECT id, action, entity_type, entity_id, actor, created_at
               FROM audit_log ORDER BY id DESC LIMIT 50"""
        ).fetchall()
    return [dict(row) for row in rows]
