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

    assert database.migrate(database_path) == 5
    assert database.migrate(database_path) == 5


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
    (migration_directory / "0007_gap.sql").write_text("SELECT 1;\n", encoding="utf-8")
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
    (migration_directory / "0005_whiteoutstats_sync.sql").unlink()

    with pytest.raises(RuntimeError, match="files are missing: 0005"):
        database.migrate(database_path)


def test_v2_database_data_is_preserved_by_multi_alliance_migration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration_directory = copy_migrations(tmp_path)
    for migration in migration_directory.glob("000[345]_*.sql"):
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
    assert database.migrate(database_path) == 5
    with sqlite3.connect(database_path) as migrated:
        assert migrated.execute("SELECT nickname FROM players WHERE fid = 'legacy-fid'").fetchone()[0] == "Legacy Player"
        assert migrated.execute("SELECT alliance_id FROM events WHERE id = 'legacy-event'").fetchone()[0] is None
        assert migrated.execute("SELECT raw_points FROM event_participants WHERE event_id = 'legacy-event'").fetchone()[0] == 0
        assert migrated.execute("SELECT actor FROM audit_log WHERE entity_id = 'legacy-event'").fetchone()[0] == "admin"
        assert migrated.execute("SELECT COUNT(*) FROM alliance_groups").fetchone()[0] == 0
        assert migrated.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
