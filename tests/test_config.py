"""Key parsing: several quotas in, one ordered list out."""

from __future__ import annotations

from pathlib import Path

import pytest

from arc_experiment.config import Config, parse_api_keys


def test_keys_are_split_and_trimmed() -> None:
    assert parse_api_keys("a, b ,c") == ("a", "b", "c")


def test_blanks_and_repeats_are_dropped() -> None:
    """A key listed twice would promise two quotas and deliver one."""
    assert parse_api_keys("a,,b, ,a") == ("a", "b")


def test_a_single_key_still_works() -> None:
    assert parse_api_keys("only") == ("only",)


def test_no_keys_is_empty_rather_than_one_blank() -> None:
    assert parse_api_keys("") == ()
    assert parse_api_keys("  ,  ") == ()


def test_the_old_single_key_variable_still_works(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Existing .env files keep working untouched."""
    env: Path = tmp_path / ".env"
    env.write_text("")
    monkeypatch.delenv("GOOGLE_API_KEYS", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "legacy")

    assert Config.from_env(env).api_keys == ("legacy",)


def test_the_plural_variable_takes_precedence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env: Path = tmp_path / ".env"
    env.write_text("")
    monkeypatch.setenv("GOOGLE_API_KEY", "legacy")
    monkeypatch.setenv("GOOGLE_API_KEYS", "new1,new2")

    assert Config.from_env(env).api_keys == ("new1", "new2")
