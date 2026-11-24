"""SQLite connections and deterministic file-based migrations."""

from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def connect(database_path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 15000")
    return connection


@contextmanager
def connection(database_path: str) -> Iterator[sqlite3.Connection]:
    database = connect(database_path)
    try:
        yield database
    finally:
        database.close()


@contextmanager
def transaction(database_path: str) -> Iterator[sqlite3.Connection]:
    connection = connect(database_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def migrate(database_path: str) -> int:
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    migration_paths = sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql"))
    versions = [int(migration_path.name.split("_", 1)[0]) for migration_path in migration_paths]
    expected_versions = list(range(1, len(versions) + 1))
    if not versions or versions != expected_versions:
        raise RuntimeError(
            "Migration files must have unique, contiguous versions starting at 0001"
        )

    connection = connect(database_path)
    try:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
              version INTEGER PRIMARY KEY,
              name TEXT NOT NULL,
              checksum TEXT NOT NULL,
              applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.commit()
        applied = {
            int(row["version"]): (row["name"], row["checksum"])
            for row in connection.execute(
                "SELECT version, name, checksum FROM schema_migrations ORDER BY version"
            )
        }
        applied_versions = sorted(applied)
        if applied_versions != list(range(1, len(applied_versions) + 1)):
            raise RuntimeError("Applied migration history is not contiguous")
        unknown_versions = set(applied) - set(versions)
        if unknown_versions:
            unknown = ", ".join(f"{version:04d}" for version in sorted(unknown_versions))
            raise RuntimeError(f"Applied migration files are missing: {unknown}")
        latest = max(applied, default=0)
        for migration_path in migration_paths:
            version = int(migration_path.name.split("_", 1)[0])
            sql = migration_path.read_text(encoding="utf-8")
            checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
            if version in applied:
                applied_name, applied_checksum = applied[version]
                if applied_name != migration_path.name or applied_checksum != checksum:
                    raise RuntimeError(f"Migration {version} was modified after it was applied")
                latest = max(latest, version)
                continue
            escaped_name = migration_path.name.replace("'", "''")
            connection.executescript(
                "BEGIN IMMEDIATE;\n"
                + sql
                + "\nINSERT INTO schema_migrations(version, name, checksum) VALUES "
                + f"({version}, '{escaped_name}', '{checksum}');\nCOMMIT;"
            )
            latest = version
        return latest
    finally:
        connection.close()


def database_is_ready(database_path: str) -> tuple[bool, int]:
    try:
        with connection(database_path) as database:
            database.execute("SELECT 1").fetchone()
            row = database.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations").fetchone()
            return True, int(row[0])
    except sqlite3.Error:
        return False, 0
