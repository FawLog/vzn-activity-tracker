from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from app import database


def copy_migrations(tmp_path: Path) -> Path:
    target = tmp_path / "migrations"
    shutil.copytree(database.MIGRATIONS_DIR, target)
    return target


def test_migrations_are_idempotent(tmp_path: Path) -> None:
    database_path = str(tmp_path / "idempotent.sqlite3")

    assert database.migrate(database_path) == 22
    assert database.migrate(database_path) == 22


def test_modified_applied_migration_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    migration_directory = copy_migrations(tmp_path)
    monkeypatch.setattr(database, "MIGRATIONS_DIR", migration_directory)
    database_path = str(tmp_path / "modified.sqlite3")
    database.migrate(database_path)

    first_migration = migration_directory / "0001_initial.sql"
    first_migration.write_text(
        first_migration.read_text(encoding="utf-8") + "\n-- modified\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="modified after it was applied"):
        database.migrate(database_path)


def test_migration_versions_must_be_contiguous(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    migration_directory = copy_migrations(tmp_path)
    (migration_directory / "0024_gap.sql").write_text("SELECT 1;\n", encoding="utf-8")
    monkeypatch.setattr(database, "MIGRATIONS_DIR", migration_directory)

    with pytest.raises(RuntimeError, match="unique, contiguous"):
        database.migrate(str(tmp_path / "gap.sqlite3"))


def test_applied_migration_file_cannot_disappear(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration_directory = copy_migrations(tmp_path)
    monkeypatch.setattr(database, "MIGRATIONS_DIR", migration_directory)
    database_path = str(tmp_path / "missing.sqlite3")
    database.migrate(database_path)
    (migration_directory / "0006_whiteoutstats_roster_completeness.sql").unlink()
    (migration_directory / "0007_normalize_whiteoutstats_avatar_hosts.sql").unlink()

    (migration_directory / "0008_event_sessions.sql").unlink()
    (migration_directory / "0009_bear_session_hosts.sql").unlink()
    (migration_directory / "0010_event_completion.sql").unlink()
    (migration_directory / "0011_foundry_session_details.sql").unlink()
    (migration_directory / "0012_calendar.sql").unlink()
    (migration_directory / "0013_state_calendar_profiles.sql").unlink()
    (migration_directory / "0014_calendar_series_rules.sql").unlink()
    (migration_directory / "0015_calendar_cycles.sql").unlink()
    (migration_directory / "0016_calendar_event_links.sql").unlink()
    (migration_directory / "0017_calendar_session_links.sql").unlink()
    (migration_directory / "0018_calendar_entry_grouping.sql").unlink()
    (migration_directory / "0019_calendar_rolling.sql").unlink()
    (migration_directory / "0020_calendar_templates.sql").unlink()
    (migration_directory / "0021_foundry_cycles.sql").unlink()
    (migration_directory / "0022_calendar_cycle_series.sql").unlink()

    with pytest.raises(RuntimeError, match="files are missing: 0006, 0007, 0008, 0009, 0010, 0011, 0012, 0013, 0014, 0015, 0016, 0017, 0018, 0019, 0020, 0021, 0022"):
        database.migrate(database_path)


def test_v2_database_data_is_preserved_by_multi_alliance_migration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration_directory = copy_migrations(tmp_path)
    for migration in [*migration_directory.glob("000[3456789]_*.sql"), *migration_directory.glob("0010_*.sql"), *migration_directory.glob("0011_*.sql"), *migration_directory.glob("0012_*.sql"), *migration_directory.glob("0013_*.sql"), *migration_directory.glob("0014_*.sql"), *migration_directory.glob("0015_*.sql"), *migration_directory.glob("0016_*.sql"), *migration_directory.glob("0017_*.sql"), *migration_directory.glob("0018_*.sql"), *migration_directory.glob("0019_*.sql"), *migration_directory.glob("0020_*.sql"), *migration_directory.glob("0021_*.sql"), *migration_directory.glob("0022_*.sql")]:
        migration.unlink()
    monkeypatch.setattr(database, "MIGRATIONS_DIR", migration_directory)
    database_path = str(tmp_path / "legacy.sqlite3")
    assert database.migrate(database_path) == 2
    with sqlite3.connect(database_path) as legacy:
        legacy.execute("INSERT INTO players(fid, nickname) VALUES ('legacy-fid', 'Legacy Player')")
        legacy.execute("INSERT INTO player_nicknames(player_fid, nickname) VALUES ('legacy-fid', 'Legacy Player')")
        legacy.execute("INSERT INTO events(id, event_type, occurred_on, status) VALUES ('legacy-event', 'foundry', '2026-01-01', 'draft')")
        legacy.execute("""INSERT INTO event_participants(event_id, player_fid, presence_status, roster_role, raw_points)
                          VALUES ('legacy-event', 'legacy-fid', 'unknown', 'main', 0)""")
        legacy.execute("INSERT INTO audit_log(action, entity_type, entity_id, actor) VALUES ('created', 'event', 'legacy-event', 'admin')")
    monkeypatch.setattr(database, "MIGRATIONS_DIR", Path(__file__).resolve().parents[1] / "migrations")
    assert database.migrate(database_path) == 22
    with sqlite3.connect(database_path) as migrated:
        assert migrated.execute("SELECT nickname FROM players WHERE fid = 'legacy-fid'").fetchone()[0] == "Legacy Player"
        assert migrated.execute("SELECT alliance_id FROM events WHERE id = 'legacy-event'").fetchone()[0] is None
        assert migrated.execute("SELECT raw_points FROM event_participants WHERE event_id = 'legacy-event'").fetchone()[0] == 0
        assert migrated.execute("SELECT actor FROM audit_log WHERE entity_id = 'legacy-event'").fetchone()[0] == "admin"
        assert migrated.execute("SELECT COUNT(*) FROM alliance_groups").fetchone()[0] == 0
        assert migrated.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_avatar_hostname_migration_is_exact_and_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration_directory = copy_migrations(tmp_path)
    (migration_directory / "0007_normalize_whiteoutstats_avatar_hosts.sql").unlink()
    monkeypatch.setattr(database, "MIGRATIONS_DIR", migration_directory)
    database_path = str(tmp_path / "avatars.sqlite3")
    (migration_directory / "0008_event_sessions.sql").unlink()
    (migration_directory / "0009_bear_session_hosts.sql").unlink()
    (migration_directory / "0010_event_completion.sql").unlink()
    (migration_directory / "0011_foundry_session_details.sql").unlink()
    (migration_directory / "0012_calendar.sql").unlink()
    (migration_directory / "0013_state_calendar_profiles.sql").unlink()
    (migration_directory / "0014_calendar_series_rules.sql").unlink()
    (migration_directory / "0015_calendar_cycles.sql").unlink()
    (migration_directory / "0016_calendar_event_links.sql").unlink()
    (migration_directory / "0017_calendar_session_links.sql").unlink()
    (migration_directory / "0018_calendar_entry_grouping.sql").unlink()
    (migration_directory / "0019_calendar_rolling.sql").unlink()
    (migration_directory / "0020_calendar_templates.sql").unlink()
    (migration_directory / "0021_foundry_cycles.sql").unlink()
    (migration_directory / "0022_calendar_cycle_series.sql").unlink()
    assert database.migrate(database_path) == 6

    obsolete = "https://gof-format-avatar.akamaized.net/avatar.png?size=64"
    canonical = "https://gof-formal-avatar.akamaized.net/avatar.png?size=64"
    unrelated = "https://gof-format-avatar.akamaized.net.example.test/avatar.png"
    with sqlite3.connect(database_path) as connection:
        for index, url in enumerate((obsolete, canonical, unrelated), start=1):
            connection.execute(
                """INSERT INTO player_whiteoutstats_profiles(player_fid, group_id, avatar_url, observed_at, received_at)
                   VALUES (?, ?, ?, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')""",
                (f"player-{index}", f"group-{index}", url),
            )
        connection.commit()

    monkeypatch.setattr(database, "MIGRATIONS_DIR", Path(__file__).resolve().parents[1] / "migrations")
    assert database.migrate(database_path) == 22
    assert database.migrate(database_path) == 22
    with sqlite3.connect(database_path) as connection:
        urls = [row[0] for row in connection.execute(
            "SELECT avatar_url FROM player_whiteoutstats_profiles ORDER BY player_fid"
        )]
    assert urls == [canonical, canonical, unrelated]


def test_foundry_migration_preserves_existing_cycle_links(tmp_path,monkeypatch):
    migration_directory=copy_migrations(tmp_path)
    (migration_directory/"0021_foundry_cycles.sql").unlink()
    (migration_directory/"0022_calendar_cycle_series.sql").unlink()
    monkeypatch.setattr(database,"MIGRATIONS_DIR",migration_directory)
    path=str(tmp_path/"cycle-migration.sqlite3")
    assert database.migrate(path)==20
    # Use a minimal valid existing group and state-scope cycle; exact original IDs survive.
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO alliance_groups(id,name,status) VALUES ('old-group','Old','active')")
        db.execute("INSERT INTO calendar_cycles(id,group_id,kind) VALUES ('old-cycle','old-group','svs')")
        db.execute("""INSERT INTO calendar_occurrences(id,group_id,cycle_id,event_type,scope,state_id,starts_at,precision,confidence,phase)
            VALUES ('old-phase','old-group','old-cycle','svs_preparation','state','1001','2026-01-01','date','confirmed','Preparation')""")
    monkeypatch.setattr(database,"MIGRATIONS_DIR",Path(__file__).resolve().parents[1]/"migrations")
    assert database.migrate(path)==22
    with database.connection(path) as db:
        assert db.execute("SELECT cycle_id FROM calendar_occurrences WHERE id='old-phase'").fetchone()[0]=="old-cycle"
        assert db.execute("SELECT kind FROM calendar_cycles WHERE id='old-cycle'").fetchone()[0]=="svs"
        assert db.execute("PRAGMA foreign_key_check").fetchall()==[]
