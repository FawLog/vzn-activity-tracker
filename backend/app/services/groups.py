"""Group and alliance operations with explicit scope validation."""

from __future__ import annotations

import sqlite3
import uuid
from typing import Any

from ..database import connection, transaction
from ..schemas import AllianceCreate, AllianceUpdate, GroupCreate, GroupUpdate


def _group_row(database: sqlite3.Connection, group_id: str) -> sqlite3.Row | None:
    return database.execute(
        """
        SELECT g.id, g.name, g.discord_server_id, g.combined_statistics, g.status,
               g.created_at, g.updated_at,
               COUNT(DISTINCT a.id) AS alliance_count,
               SUM(CASE WHEN a.alliance_type = 'primary' THEN 1 ELSE 0 END) AS primary_count
        FROM alliance_groups g
        LEFT JOIN alliances a ON a.group_id = g.id
        WHERE g.id = ?
        GROUP BY g.id
        """,
        (group_id,),
    ).fetchone()


def onboarding_status(database_path: str) -> dict[str, Any]:
    with connection(database_path) as database:
        group_count = int(database.execute("SELECT COUNT(*) FROM alliance_groups").fetchone()[0])
        legacy_events = int(
            database.execute("SELECT COUNT(*) FROM events WHERE alliance_id IS NULL").fetchone()[0]
        )
    return {
        "required": group_count == 0,
        "group_count": group_count,
        "unassigned_legacy_events": legacy_events,
    }


def _create_group(
    database: sqlite3.Connection,
    payload: GroupCreate,
    *,
    require_empty_groups: bool,
    sync_enabled: bool = False,
    whiteoutstats_alliance_id: str | None = None,
) -> dict[str, Any]:
    if require_empty_groups and database.execute("SELECT 1 FROM alliance_groups LIMIT 1").fetchone():
        raise ValueError("Initial onboarding has already been completed")

    if not require_empty_groups and not database.execute("SELECT 1 FROM alliance_groups LIMIT 1").fetchone():
        raise ValueError("Create the first group through initial onboarding")

    legacy_events = int(database.execute("SELECT COUNT(*) FROM events WHERE alliance_id IS NULL").fetchone()[0])
    if payload.assign_legacy_events and not payload.confirm_legacy_assignment:
        raise ValueError("Legacy event assignment requires explicit confirmation")
    if legacy_events and require_empty_groups and not payload.assign_legacy_events:
        raise ValueError("Confirm whether legacy events should be assigned before completing onboarding")

    group_id = uuid.uuid4().hex
    alliance_id = uuid.uuid4().hex
    database.execute(
        """
        INSERT INTO alliance_groups(id, name, discord_server_id, combined_statistics)
        VALUES (?, ?, ?, ?)
        """,
        (group_id, payload.name, payload.discord_server_id, int(payload.combined_statistics)),
    )
    database.execute(
        """
        INSERT INTO alliances(id, group_id, name, tag, state_id, alliance_type)
        VALUES (?, ?, ?, ?, ?, 'primary')
        """,
        (
            alliance_id,
            group_id,
            payload.primary_alliance_name,
            payload.primary_alliance_tag,
            payload.primary_alliance_state_id,
        ),
    )
    database.execute(
        """INSERT INTO alliance_sync_settings(alliance_id, whiteoutstats_alliance_id, sync_enabled, sync_interval_minutes)
           VALUES (?, ?, ?, 720)""",
        (alliance_id, whiteoutstats_alliance_id, int(sync_enabled)),
    )

    if require_empty_groups:
        database.execute(
            """
            INSERT INTO player_group_profiles(player_fid, group_id, status, source_type, source_note)
            SELECT fid, ?, 'unconfirmed', 'legacy_unconfirmed',
                   'Legacy player record was retained without inferred alliance membership'
            FROM players
            """,
            (group_id,),
        )
    if payload.assign_legacy_events:
        database.execute("UPDATE events SET alliance_id = ? WHERE alliance_id IS NULL", (alliance_id,))

    database.execute(
        """
        INSERT INTO audit_log(action, entity_type, entity_id, actor)
        VALUES ('created', 'alliance_group', ?, 'admin')
        """,
        (group_id,),
    )
    database.execute(
        """
        INSERT INTO audit_log(action, entity_type, entity_id, actor)
        VALUES ('created', 'alliance', ?, 'admin')
        """,
        (alliance_id,),
    )
    if payload.assign_legacy_events and legacy_events:
        database.execute(
            """
            INSERT INTO audit_log(action, entity_type, entity_id, actor)
            VALUES ('legacy_events_assigned', 'alliance', ?, 'admin')
            """,
            (alliance_id,),
        )
    result = _group_row(database, group_id)
    if result is None:
        raise RuntimeError("Group was not persisted")
    return dict(result)


def create_group(
    database_path: str,
    payload: GroupCreate,
    *,
    onboarding: bool = False,
    sync_enabled: bool = False,
    whiteoutstats_alliance_id: str | None = None,
) -> dict[str, Any]:
    with transaction(database_path) as database:
        return _create_group(
            database,
            payload,
            require_empty_groups=onboarding,
            sync_enabled=sync_enabled,
            whiteoutstats_alliance_id=whiteoutstats_alliance_id,
        )


def list_groups(database_path: str) -> list[dict[str, Any]]:
    with connection(database_path) as database:
        rows = database.execute(
            """
            SELECT g.id, g.name, g.discord_server_id, g.combined_statistics, g.status,
                   g.created_at, g.updated_at, COUNT(a.id) AS alliance_count,
                   SUM(CASE WHEN a.alliance_type = 'primary' THEN 1 ELSE 0 END) AS primary_count
            FROM alliance_groups g
            LEFT JOIN alliances a ON a.group_id = g.id
            GROUP BY g.id
            ORDER BY CASE g.status WHEN 'active' THEN 0 ELSE 1 END, g.name COLLATE NOCASE
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_group(database_path: str, group_id: str) -> dict[str, Any] | None:
    with connection(database_path) as database:
        row = _group_row(database, group_id)
    return dict(row) if row else None


def update_group(database_path: str, group_id: str, payload: GroupUpdate) -> dict[str, Any] | None:
    with transaction(database_path) as database:
        existing = _group_row(database, group_id)
        if existing is None:
            return None
        if existing["status"] == "archived" and payload.status != "active":
            raise ValueError("Restore the archived group before changing its settings")
        if payload.status == "archived" and not payload.confirm_archive:
            raise ValueError("Archiving a group requires explicit confirmation")
        values: dict[str, Any] = {}
        if "name" in payload.model_fields_set:
            values["name"] = payload.name
        if "discord_server_id" in payload.model_fields_set:
            values["discord_server_id"] = payload.discord_server_id
        if payload.combined_statistics is not None:
            values["combined_statistics"] = int(payload.combined_statistics)
        if payload.status is not None:
            values["status"] = payload.status
        if values:
            assignments = ", ".join(f"{column} = ?" for column in values)
            database.execute(
                f"UPDATE alliance_groups SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (*values.values(), group_id),
            )
            database.execute(
                """
                INSERT INTO audit_log(action, entity_type, entity_id, actor)
                VALUES ('updated', 'alliance_group', ?, 'admin')
                """,
                (group_id,),
            )
        updated = _group_row(database, group_id)
    return dict(updated) if updated else None


def list_alliances(database_path: str, group_id: str) -> list[dict[str, Any]] | None:
    with connection(database_path) as database:
        if _group_row(database, group_id) is None:
            return None
        rows = database.execute(
            """
            SELECT a.id, a.group_id, a.name, a.tag, a.state_id, a.alliance_type, a.status,
                   a.created_at, a.updated_at, s.whiteoutstats_alliance_id, s.sync_enabled,
                   s.sync_interval_minutes, s.last_sync_at, s.last_attempt_at, s.last_sync_status, s.last_sync_error,
                   s.sync_in_progress_at, s.last_found_count, s.last_added_count, s.last_updated_count
            FROM alliances a
            JOIN alliance_sync_settings s ON s.alliance_id = a.id
            WHERE a.group_id = ?
            ORDER BY CASE a.alliance_type WHEN 'primary' THEN 0 ELSE 1 END, a.name COLLATE NOCASE
            """,
            (group_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_alliance(database_path: str, group_id: str, alliance_id: str) -> dict[str, Any] | None:
    with connection(database_path) as database:
        row = database.execute(
            """
            SELECT a.id, a.group_id, a.name, a.tag, a.state_id, a.alliance_type, a.status,
                   a.created_at, a.updated_at, s.whiteoutstats_alliance_id, s.sync_enabled
            FROM alliances a JOIN alliance_sync_settings s ON s.alliance_id = a.id
            WHERE a.id = ? AND a.group_id = ?
            """,
            (alliance_id, group_id),
        ).fetchone()
    return dict(row) if row else None


def create_additional_alliance(
    database_path: str,
    group_id: str,
    payload: AllianceCreate,
    *,
    sync_enabled: bool = False,
    whiteoutstats_alliance_id: str | None = None,
) -> dict[str, Any] | None:
    alliance_id = uuid.uuid4().hex
    with transaction(database_path) as database:
        group = _group_row(database, group_id)
        if group is None:
            return None
        if group["status"] != "active":
            raise ValueError("Cannot add an alliance to an archived group")
        database.execute(
            """
            INSERT INTO alliances(id, group_id, name, tag, state_id, alliance_type)
            VALUES (?, ?, ?, ?, ?, 'additional')
            """,
            (alliance_id, group_id, payload.name, payload.tag, payload.state_id),
        )
        database.execute(
            """INSERT INTO alliance_sync_settings(alliance_id, whiteoutstats_alliance_id, sync_enabled, sync_interval_minutes)
               VALUES (?, ?, ?, 720)""",
            (alliance_id, whiteoutstats_alliance_id, int(sync_enabled)),
        )
        database.execute(
            """
            INSERT INTO audit_log(action, entity_type, entity_id, actor)
            VALUES ('created', 'alliance', ?, 'admin')
            """,
            (alliance_id,),
        )
        row = database.execute("SELECT * FROM alliances WHERE id = ?", (alliance_id,)).fetchone()
    return dict(row) if row else None


def connect_whiteoutstats_alliance(
    database_path: str,
    group_id: str,
    alliance_id: str,
    whiteoutstats_alliance_id: str,
    *,
    sync_enabled: bool,
) -> dict[str, Any] | None:
    with transaction(database_path) as database:
        row = database.execute(
            """SELECT a.id FROM alliances a JOIN alliance_groups g ON g.id = a.group_id
               WHERE a.id = ? AND a.group_id = ? AND a.status = 'active' AND g.status = 'active'""",
            (alliance_id, group_id),
        ).fetchone()
        if row is None:
            return None
        database.execute(
            """UPDATE alliance_sync_settings
               SET whiteoutstats_alliance_id = ?, sync_enabled = ?, sync_interval_minutes = 720,
                   updated_at = CURRENT_TIMESTAMP
               WHERE alliance_id = ?""",
            (whiteoutstats_alliance_id, int(sync_enabled), alliance_id),
        )
        database.execute(
            """INSERT INTO audit_log(action, entity_type, entity_id, actor)
               VALUES ('whiteoutstats_connected', 'alliance', ?, 'admin')""",
            (alliance_id,),
        )
    return get_alliance(database_path, group_id, alliance_id)


def update_alliance(
    database_path: str,
    group_id: str,
    alliance_id: str,
    payload: AllianceUpdate,
) -> dict[str, Any] | None:
    with transaction(database_path) as database:
        group = _group_row(database, group_id)
        if group is None:
            return None
        if group["status"] != "active":
            raise ValueError("Restore the archived group before changing alliances")
        existing = database.execute(
            "SELECT * FROM alliances WHERE id = ? AND group_id = ?", (alliance_id, group_id)
        ).fetchone()
        if existing is None:
            return None
        if existing["status"] == "archived" and payload.status != "active":
            raise ValueError("Restore the archived alliance before changing its settings")
        if payload.status == "archived":
            if not payload.confirm_archive:
                raise ValueError("Archiving an alliance requires explicit confirmation")
            if existing["alliance_type"] == "primary":
                raise ValueError("Archive the group instead of its primary alliance")
        values = {
            key: value
            for key, value in {
                "name": payload.name,
                "tag": payload.tag,
                "state_id": payload.state_id,
                "status": payload.status,
            }.items()
            if value is not None
        }
        if values:
            assignments = ", ".join(f"{column} = ?" for column in values)
            database.execute(
                f"UPDATE alliances SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (*values.values(), alliance_id),
            )
            database.execute(
                """
                INSERT INTO audit_log(action, entity_type, entity_id, actor)
                VALUES ('updated', 'alliance', ?, 'admin')
                """,
                (alliance_id,),
            )
        updated = database.execute("SELECT * FROM alliances WHERE id = ?", (alliance_id,)).fetchone()
    return dict(updated) if updated else None
