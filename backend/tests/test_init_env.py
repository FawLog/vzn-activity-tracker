from __future__ import annotations

import stat
import sys

import pytest

from scripts import init_env


def test_init_env_can_write_to_a_private_staging_path(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "pending.env"
    answers = iter(["correct-horse-battery-staple", "correct-horse-battery-staple"])
    monkeypatch.setattr(init_env.getpass, "getpass", lambda _prompt: next(answers))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "init_env.py",
            "--domain",
            "vzn.fawlog.cc",
            "--image-tag",
            "ci-" + "a" * 40,
            "--output",
            str(target),
        ],
    )

    init_env.main()

    content = target.read_text(encoding="utf-8")
    assert 'ALLOWED_HOSTS="vzn.fawlog.cc,localhost,127.0.0.1"' in content
    assert f'VZN_IMAGE_TAG="ci-{"a" * 40}"' in content
    assert "correct-horse-battery-staple" not in content
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_init_env_refuses_to_overwrite_explicit_output(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "pending.env"
    target.write_text("existing\n", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        ["init_env.py", "--output", str(target)],
    )

    with pytest.raises(SystemExit):
        init_env.main()

    assert target.read_text(encoding="utf-8") == "existing\n"
