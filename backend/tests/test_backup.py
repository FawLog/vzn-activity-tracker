from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app import backup, database


def player_count(database_path: Path) -> int:
    with sqlite3.connect(database_path) as connection:
        return int(connection.execute("SELECT COUNT(*) FROM players").fetchone()[0])


def test_backup_verify_and_restore_preserve_a_consistent_snapshot(tmp_path: Path) -> None:
    database_path = tmp_path / "tracker.sqlite3"
    database.migrate(str(database_path))
    with sqlite3.connect(database_path) as connection:
        connection.execute("INSERT INTO players(fid, nickname) VALUES (?, ?)", ("1001", "Before backup"))
        connection.commit()

    backup_path = backup.backup(database_path, tmp_path / "backups")
    backup.verify(backup_path)

    with sqlite3.connect(database_path) as connection:
        connection.execute("INSERT INTO players(fid, nickname) VALUES (?, ?)", ("1002", "After backup"))
        connection.commit()

    backup.restore(backup_path, database_path)

    assert database.migrate(str(database_path)) == 8
    assert player_count(database_path) == 1
    with sqlite3.connect(database_path) as connection:
        restored_player = connection.execute("SELECT fid, nickname FROM players").fetchone()
    assert restored_player == ("1001", "Before backup")


def test_restore_rejects_corrupt_backup_without_replacing_database(tmp_path: Path) -> None:
    database_path = tmp_path / "tracker.sqlite3"
    database.migrate(str(database_path))
    with sqlite3.connect(database_path) as connection:
        connection.execute("INSERT INTO players(fid, nickname) VALUES (?, ?)", ("1001", "Original"))
        connection.commit()

    corrupt_backup = tmp_path / "corrupt.sqlite3"
    corrupt_backup.write_bytes(b"not a sqlite database")

    with pytest.raises((sqlite3.DatabaseError, RuntimeError)):
        backup.restore(corrupt_backup, database_path)

    assert player_count(database_path) == 1
