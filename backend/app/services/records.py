"""Explicit data-access operations for roster, events, and audit records."""

from __future__ import annotations

import sqlite3
import uuid
from typing import Any

from ..database import connection, transaction
from ..schemas import EventCreate, PlayerCreate

PLAYER_SORT_COLUMNS = {"fid": "fid", "nickname": "nickname", "created_at": "created_at"}
EVENT_SORT_COLUMNS = {"occurred_on": "occurred_on", "event_type": "event_type", "status": "status"}


def overview(database_path: str) -> dict[str, Any]:
    with connection(database_path) as database:
        players = database.execute("SELECT COUNT(*) FROM players").fetchone()[0]
        events = database.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        published = database.execute(
            "SELECT COUNT(*) FROM events WHERE status = 'published'"
        ).fetchone()[0]
        recent = database.execute(
            """
            SELECT e.id, e.event_type, e.occurred_on, e.status, e.created_at, e.updated_at,
                   COUNT(ep.id) AS participant_count
            FROM events e
            LEFT JOIN event_participants ep ON ep.event_id = e.id
            GROUP BY e.id
            ORDER BY e.occurred_on DESC, e.created_at DESC
            LIMIT 5
            """
        ).fetchall()
    return {
        "players": players,
        "events": events,
        "published_events": published,
        "recent_events": [dict(row) for row in recent],
    }


def list_players(
    database_path: str,
    *,
    query: str = "",
    sort: str = "nickname",
    direction: str = "asc",
) -> list[dict[str, Any]]:
    sort_column = PLAYER_SORT_COLUMNS.get(sort, "nickname")
    sort_direction = "DESC" if direction == "desc" else "ASC"
    pattern = f"%{query.strip()}%"
    with connection(database_path) as database:
        rows = database.execute(
            f"""
            SELECT fid, nickname, created_at, updated_at
            FROM players
            WHERE ? = '' OR fid LIKE ? OR nickname LIKE ?
            ORDER BY {sort_column} {sort_direction}, fid ASC
            LIMIT 100
            """,
            (query.strip(), pattern, pattern),
        ).fetchall()
    return [dict(row) for row in rows]


def get_player(database_path: str, fid: str) -> dict[str, Any] | None:
    with connection(database_path) as database:
        player = database.execute(
            "SELECT fid, nickname, created_at, updated_at FROM players WHERE fid = ?",
            (fid,),
        ).fetchone()
        if player is None:
            return None
        nicknames = database.execute(
            """
            SELECT nickname, valid_from, valid_to
            FROM player_nicknames
            WHERE player_fid = ?
            ORDER BY valid_from DESC
            """,
            (fid,),
        ).fetchall()
        memberships = database.execute(
            """
            SELECT joined_on, left_on
            FROM player_memberships
            WHERE player_fid = ?
            ORDER BY joined_on DESC
            """,
            (fid,),
        ).fetchall()
    result = dict(player)
    result["nickname_history"] = [dict(row) for row in nicknames]
    result["memberships"] = [dict(row) for row in memberships]
    return result


def create_player(database_path: str, payload: PlayerCreate) -> dict[str, Any]:
    try:
        with transaction(database_path) as connection:
            connection.execute(
                "INSERT INTO players(fid, nickname) VALUES (?, ?)",
                (payload.fid, payload.nickname),
            )
            connection.execute(
                "INSERT INTO player_nicknames(player_fid, nickname) VALUES (?, ?)",
                (payload.fid, payload.nickname),
            )
            connection.execute(
                """
                INSERT INTO audit_log(action, entity_type, entity_id, actor)
                VALUES ('created', 'player', ?, 'admin')
                """,
                (payload.fid,),
            )
    except sqlite3.IntegrityError as error:
        raise ValueError("A player with this FID already exists") from error
    player = get_player(database_path, payload.fid)
    if player is None:
        raise RuntimeError("Player was not persisted")
    return player


def list_events(
    database_path: str,
    *,
    sort: str = "occurred_on",
    direction: str = "desc",
) -> list[dict[str, Any]]:
    sort_column = EVENT_SORT_COLUMNS.get(sort, "occurred_on")
    sort_direction = "ASC" if direction == "asc" else "DESC"
    with connection(database_path) as database:
        rows = database.execute(
            f"""
            SELECT e.id, e.event_type, e.occurred_on, e.status, e.created_at, e.updated_at,
                   COUNT(ep.id) AS participant_count
            FROM events e
            LEFT JOIN event_participants ep ON ep.event_id = e.id
            GROUP BY e.id
            ORDER BY {sort_column} {sort_direction}, e.created_at DESC
            LIMIT 100
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_event(database_path: str, event_id: str) -> dict[str, Any] | None:
    with connection(database_path) as database:
        event = database.execute(
            """
            SELECT id, event_type, occurred_on, status, created_at, updated_at
            FROM events WHERE id = ?
            """,
            (event_id,),
        ).fetchone()
        if event is None:
            return None
        participants = database.execute(
            """
            SELECT ep.player_fid AS fid, p.nickname, ep.presence_status,
                   ep.roster_role, ep.raw_points, ep.source_complete
            FROM event_participants ep
            JOIN players p ON p.fid = ep.player_fid
            WHERE ep.event_id = ?
            ORDER BY p.nickname COLLATE NOCASE
            """,
            (event_id,),
        ).fetchall()
    result = dict(event)
    result["participants"] = [dict(row) for row in participants]
    return result


def create_event(database_path: str, payload: EventCreate) -> dict[str, Any]:
    event_id = uuid.uuid4().hex
    with transaction(database_path) as connection:
        connection.execute(
            "INSERT INTO events(id, event_type, occurred_on, status) VALUES (?, ?, ?, ?)",
            (event_id, payload.event_type.value, payload.occurred_on.isoformat(), payload.status.value),
        )
        connection.execute(
            """
            INSERT INTO audit_log(action, entity_type, entity_id, actor)
            VALUES ('created', 'event', ?, 'admin')
            """,
            (event_id,),
        )
    event = get_event(database_path, event_id)
    if event is None:
        raise RuntimeError("Event was not persisted")
    return event


def list_audit(database_path: str) -> list[dict[str, Any]]:
    with connection(database_path) as database:
        rows = database.execute(
            """
            SELECT id, action, entity_type, entity_id, actor, created_at
            FROM audit_log
            ORDER BY id DESC
            LIMIT 50
            """
        ).fetchall()
    return [dict(row) for row in rows]
