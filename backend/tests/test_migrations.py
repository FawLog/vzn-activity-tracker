from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app import database


def copy_migrations(tmp_path: Path) -> Path:
    target = tmp_path / "migrations"
    shutil.copytree(database.MIGRATIONS_DIR, target)
    return target


def test_migrations_are_idempotent(tmp_path: Path) -> None:
    database_path = str(tmp_path / "idempotent.sqlite3")

    assert database.migrate(database_path) == 2
    assert database.migrate(database_path) == 2


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
    (migration_directory / "0004_gap.sql").write_text("SELECT 1;\n", encoding="utf-8")
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
    (migration_directory / "0002_security_cleanup_indexes.sql").unlink()

    with pytest.raises(RuntimeError, match="files are missing: 0002"):
        database.migrate(database_path)
