"""Explicit, group-scoped data-access operations for roster, events, and audit records."""

from __future__ import annotations

import sqlite3
import uuid
from typing import Any

from ..database import connection, transaction
from ..schemas import EventCreate, PlayerCreate

PLAYER_SORT_COLUMNS = {"fid": "p.fid", "nickname": "p.nickname", "created_at": "p.created_at"}
EVENT_SORT_COLUMNS = {"occurred_on": "e.occurred_on", "event_type": "e.event_type", "status": "e.status"}


def _group_exists(database: sqlite3.Connection, group_id: str) -> bool:
    return bool(database.execute("SELECT 1 FROM alliance_groups WHERE id = ?", (group_id,)).fetchone())


def _alliance_in_group(database: sqlite3.Connection, group_id: str, alliance_id: str) -> bool:
    return bool(
        database.execute(
            "SELECT 1 FROM alliances WHERE id = ? AND group_id = ?", (alliance_id, group_id)
        ).fetchone()
    )


def overview(database_path: str, group_id: str) -> dict[str, Any] | None:
    with connection(database_path) as database:
        if not _group_exists(database, group_id):
            return None
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
                   e.status, e.created_at, e.updated_at, COUNT(ep.id) AS participant_count
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
    return {"players": players, "events": events, "published_events": published, "recent_events": [dict(row) for row in recent]}


def list_players(
    database_path: str,
    group_id: str,
    *,
    alliance_id: str | None = None,
    query: str = "",
    sort: str = "nickname",
    direction: str = "asc",
) -> list[dict[str, Any]] | None:
    sort_column = PLAYER_SORT_COLUMNS.get(sort, "p.nickname")
    sort_direction = "DESC" if direction == "desc" else "ASC"
    pattern = f"%{query.strip()}%"
    with connection(database_path) as database:
        if not _group_exists(database, group_id):
            return None
        if alliance_id and not _alliance_in_group(database, group_id, alliance_id):
            raise ValueError("Alliance does not belong to this group")
        rows = database.execute(
            f"""
            SELECT p.fid, p.nickname, p.created_at, p.updated_at, pgp.status AS group_status,
                   pgp.primary_alliance_id
            FROM player_group_profiles pgp
            JOIN players p ON p.fid = pgp.player_fid
            WHERE pgp.group_id = ?
              AND (? IS NULL OR pgp.primary_alliance_id = ?)
              AND (? = '' OR p.fid LIKE ? OR p.nickname LIKE ?)
            ORDER BY {sort_column} {sort_direction}, p.fid ASC
            LIMIT 100
            """,
            (group_id, alliance_id, alliance_id, query.strip(), pattern, pattern),
        ).fetchall()
    return [dict(row) for row in rows]


def get_player(database_path: str, group_id: str, fid: str) -> dict[str, Any] | None:
    with connection(database_path) as database:
        profile = database.execute(
            """
            SELECT p.fid, p.nickname, p.created_at, p.updated_at, pgp.status AS group_status,
                   pgp.primary_alliance_id, a.name AS primary_alliance_name
            FROM player_group_profiles pgp
            JOIN players p ON p.fid = pgp.player_fid
            LEFT JOIN alliances a ON a.id = pgp.primary_alliance_id
            WHERE pgp.group_id = ? AND pgp.player_fid = ?
            """,
            (group_id, fid),
        ).fetchone()
        if profile is None:
            return None
        nicknames = database.execute(
            """
            SELECT nickname, valid_from, valid_to FROM player_nicknames
            WHERE player_fid = ? ORDER BY valid_from DESC
            """,
            (fid,),
        ).fetchall()
        memberships = database.execute(
            """
            SELECT joined_on, left_on FROM player_memberships
            WHERE player_fid = ? ORDER BY joined_on DESC
            """,
            (fid,),
        ).fetchall()
    result = dict(profile)
    result["nickname_history"] = [dict(row) for row in nicknames]
    result["legacy_memberships"] = [dict(row) for row in memberships]
    return result


def create_player(database_path: str, group_id: str, payload: PlayerCreate) -> dict[str, Any]:
    try:
        with transaction(database_path) as database:
            if not _group_exists(database, group_id):
                raise LookupError("Group not found")
            existing = database.execute("SELECT 1 FROM players WHERE fid = ?", (payload.fid,)).fetchone()
            if existing is None:
                database.execute("INSERT INTO players(fid, nickname) VALUES (?, ?)", (payload.fid, payload.nickname))
                database.execute(
                    "INSERT INTO player_nicknames(player_fid, nickname) VALUES (?, ?)",
                    (payload.fid, payload.nickname),
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
                INSERT INTO player_group_profiles(player_fid, group_id, status, source_type)
                VALUES (?, ?, 'unconfirmed', 'manual')
                """,
                (payload.fid, group_id),
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
                   e.created_at, e.updated_at, COUNT(ep.id) AS participant_count
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
            SELECT ep.player_fid AS fid, p.nickname, ep.presence_status, ep.roster_role,
                   ep.raw_points, ep.source_complete
            FROM event_participants ep JOIN players p ON p.fid = ep.player_fid
            WHERE ep.event_id = ? ORDER BY p.nickname COLLATE NOCASE
            """,
            (event_id,),
        ).fetchall()
    result = dict(event)
    result["participants"] = [dict(row) for row in participants]
    return result


def create_event(database_path: str, group_id: str, alliance_id: str, payload: EventCreate) -> dict[str, Any]:
    event_id = uuid.uuid4().hex
    with transaction(database_path) as database:
        if not _alliance_in_group(database, group_id, alliance_id):
            raise LookupError("Alliance not found in selected group")
        database.execute(
            """
            INSERT INTO events(id, alliance_id, event_type, occurred_on, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (event_id, alliance_id, payload.event_type.value, payload.occurred_on.isoformat(), payload.status.value),
        )
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
