"""Online SQLite backup and integrity verification for the production volume."""

from __future__ import annotations

import argparse
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


def backup(source: Path, destination_directory: Path) -> Path:
    destination_directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    destination = destination_directory / f"vzn-{timestamp}.sqlite3"
    if destination.exists():
        raise RuntimeError(f"Backup already exists: {destination}")
    with sqlite3.connect(source) as source_database, sqlite3.connect(destination) as backup_database:
        source_database.backup(backup_database)
        integrity = backup_database.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"Backup integrity check failed: {integrity}")
    return destination


def verify(target: Path) -> None:
    with sqlite3.connect(f"file:{target}?mode=ro", uri=True) as database:
        result = database.execute("PRAGMA integrity_check").fetchone()[0]
    if result != "ok":
        raise RuntimeError(f"Integrity check failed: {result}")


def main() -> None:
    parser = argparse.ArgumentParser()
    subcommands = parser.add_subparsers(dest="command", required=True)
    create = subcommands.add_parser("create")
    create.add_argument("--database", type=Path, default=Path("/data/vzn.sqlite3"))
    create.add_argument("--destination", type=Path, default=Path("/data/backups"))
    check = subcommands.add_parser("verify")
    check.add_argument("backup", type=Path)
    arguments = parser.parse_args()
    if arguments.command == "create":
        print(backup(arguments.database, arguments.destination))
    else:
        verify(arguments.backup)
        print("ok")


if __name__ == "__main__":
    main()
