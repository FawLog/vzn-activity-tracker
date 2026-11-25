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
    affiliation: str | None = None,
    query: str = "",
    sort: str = "nickname",
    direction: str = "asc",
) -> list[dict[str, Any]] | None:
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
        rows = database.execute(
            f"""
            SELECT pgp.player_fid AS fid, pno.nickname, pgp.created_at, pgp.updated_at,
                   pgp.status AS group_status, pgp.primary_alliance_id,
                   primary_alliance.name AS primary_alliance_name
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
            WHERE pgp.group_id = ?
              AND {affiliation_condition}
              AND (? = '' OR pgp.player_fid LIKE ? OR pno.nickname LIKE ?)
            ORDER BY {sort_column} {sort_direction}, pgp.player_fid ASC
            LIMIT 100
            """,
            parameters,
        ).fetchall()
    return [dict(row) for row in rows]


def get_player(database_path: str, group_id: str, fid: str) -> dict[str, Any] | None:
    with connection(database_path) as database:
        profile = database.execute(
            """
            SELECT pgp.player_fid AS fid, pno.nickname, pgp.created_at, pgp.updated_at, pgp.status AS group_status,
                   pgp.primary_alliance_id, a.name AS primary_alliance_name
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
    result = dict(profile)
    result["nickname_history"] = [dict(row) for row in nicknames]
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
