from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts import set_image_tag


@pytest.fixture
def environment_file(tmp_path: Path) -> Path:
    target = tmp_path / ".env"
    target.write_text(
        'SESSION_SECRET="unchanged-secret"\nADMIN_PASSWORD_HASH="unchanged-hash"\n'
        'VZN_IMAGE_TAG="ci-old"\n',
        encoding="utf-8",
    )
    target.chmod(0o600)
    return target


def test_set_image_tag_changes_only_the_tag_and_preserves_mode(environment_file: Path) -> None:
    before = environment_file.read_text(encoding="utf-8")
    owner = (os.geteuid(), os.getegid())
    set_image_tag.set_image_tag(environment_file, "ci-new", expected_owner=owner)

    after = environment_file.read_text(encoding="utf-8")
    assert after.replace('VZN_IMAGE_TAG="ci-new"', 'VZN_IMAGE_TAG="ci-old"') == before
    assert set_image_tag.read_image_tag(environment_file, expected_owner=owner) == "ci-new"
    assert environment_file.stat().st_mode & 0o777 == 0o600


def test_set_image_tag_rejects_duplicate_tag_definition(environment_file: Path) -> None:
    with environment_file.open("a", encoding="utf-8") as output:
        output.write('VZN_IMAGE_TAG="ci-other"\n')

    with pytest.raises(RuntimeError, match="exactly once"):
        set_image_tag.set_image_tag(
            environment_file,
            "ci-new",
            expected_owner=(os.geteuid(), os.getegid()),
        )
