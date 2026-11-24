#!/usr/bin/env python3
"""Create the production environment file without exposing credentials."""

from __future__ import annotations

import argparse
import getpass
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.security import hash_password  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", default="vzn.fawlog.cc")
    parser.add_argument("--image-tag", default="0.1.0")
    parser.add_argument(
        "--output",
        type=Path,
        help="Write the environment file to this path instead of the application root",
    )
    arguments = parser.parse_args()
    if not arguments.domain or any(character in arguments.domain for character in "/:* "):
        parser.error("--domain must be a hostname without a scheme or port")

    target = arguments.output if arguments.output is not None else ROOT / ".env"
    if target.exists():
        parser.error(f"{target} already exists; refusing to overwrite it")
    if not target.parent.is_dir():
        parser.error(f"output directory does not exist: {target.parent}")

    password = getpass.getpass("Administrator password (at least 14 characters): ")
    confirmation = getpass.getpass("Repeat administrator password: ")
    if password != confirmation:
        parser.error("Passwords do not match")
    try:
        password_hash = hash_password(password)
    except ValueError as error:
        parser.error(str(error))

    values = {
        "APP_NAME": "VZN Activity Tracker",
        "APP_ENV": "production",
        "ALLOWED_HOSTS": f"{arguments.domain},localhost,127.0.0.1",
        "TRUSTED_PROXIES": "127.0.0.1,::1",
        "DATABASE_PATH": "/data/vzn.sqlite3",
        "SESSION_SECRET": secrets.token_urlsafe(48),
        "ADMIN_PASSWORD_HASH": password_hash,
        "SECURE_COOKIES": "1",
        "SESSION_TTL_SECONDS": "28800",
        "LOGIN_WINDOW_SECONDS": "900",
        "LOGIN_MAX_ATTEMPTS": "5",
        "VZN_IMAGE_TAG": arguments.image_tag,
    }
    lines = []
    for key, value in values.items():
        quote = "'" if key == "ADMIN_PASSWORD_HASH" else '"'
        lines.append(f"{key}={quote}{value}{quote}")
    content = "\n".join(lines) + "\n"
    file_descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(file_descriptor, "w", encoding="utf-8") as environment_file:
        environment_file.write(content)
    print(f"Created {target} with mode 0600.")


if __name__ == "__main__":
    main()
