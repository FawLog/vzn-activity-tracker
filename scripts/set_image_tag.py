#!/usr/bin/env python3
"""Read or atomically replace only VZN_IMAGE_TAG in a root-owned .env file."""

from __future__ import annotations

import argparse
import os
import re
import stat
import tempfile
from pathlib import Path
from typing import Final

IMAGE_TAG_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
ROOT_OWNER: Final = (0, 0)


def read_lines(environment_file: Path, *, expected_owner: tuple[int, int] = ROOT_OWNER) -> list[str]:
    metadata = environment_file.stat()
    if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600:
        raise RuntimeError("Environment file must be a regular file with mode 0600")
    if (metadata.st_uid, metadata.st_gid) != expected_owner:
        raise RuntimeError("Environment file must be owned by root:root")
    return environment_file.read_text(encoding="utf-8").splitlines(keepends=True)


def image_tag_line_index(lines: list[str]) -> int:
    matches = [index for index, line in enumerate(lines) if line.startswith("VZN_IMAGE_TAG=")]
    if len(matches) != 1:
        raise RuntimeError("Environment file must define VZN_IMAGE_TAG exactly once")
    return matches[0]


def parse_image_tag(line: str) -> str:
    value = line.removeprefix("VZN_IMAGE_TAG=").rstrip("\r\n")
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    if not IMAGE_TAG_PATTERN.fullmatch(value):
        raise RuntimeError("VZN_IMAGE_TAG contains unsupported characters")
    return value


def read_image_tag(environment_file: Path, *, expected_owner: tuple[int, int] = ROOT_OWNER) -> str:
    lines = read_lines(environment_file, expected_owner=expected_owner)
    return parse_image_tag(lines[image_tag_line_index(lines)])


def set_image_tag(
    environment_file: Path,
    image_tag: str,
    *,
    expected_owner: tuple[int, int] = ROOT_OWNER,
) -> None:
    if not IMAGE_TAG_PATTERN.fullmatch(image_tag):
        raise ValueError("Image tag contains unsupported characters")
    lines = read_lines(environment_file, expected_owner=expected_owner)
    index = image_tag_line_index(lines)
    newline = "\r\n" if lines[index].endswith("\r\n") else "\n"
    lines[index] = f'VZN_IMAGE_TAG="{image_tag}"{newline}'

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".vzn-image-tag.", dir=environment_file.parent
    )
    temporary_file = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as output:
            output.writelines(lines)
            output.flush()
            os.fsync(output.fileno())
        os.chown(temporary_file, *expected_owner)
        os.replace(temporary_file, environment_file)
    except BaseException:
        temporary_file.unlink(missing_ok=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    subcommands = parser.add_subparsers(dest="command", required=True)
    read = subcommands.add_parser("read")
    read.add_argument("environment_file", type=Path)
    replace = subcommands.add_parser("set")
    replace.add_argument("environment_file", type=Path)
    replace.add_argument("image_tag")
    arguments = parser.parse_args()

    if arguments.command == "read":
        print(read_image_tag(arguments.environment_file))
    else:
        set_image_tag(arguments.environment_file, arguments.image_tag)


if __name__ == "__main__":
    main()
