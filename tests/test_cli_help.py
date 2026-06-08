from __future__ import annotations

import re

from typer.testing import CliRunner

from jobforge.cli import app

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _plain(text: str) -> str:
    return _ANSI.sub("", text)


def test_top_level_help_lists_commands() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0, result.output
    out = _plain(result.output)
    assert "ingest" in out
    assert "tailor" in out


def test_tailor_help_shows_required_flags() -> None:
    result = CliRunner().invoke(app, ["tailor", "--help"])
    assert result.exit_code == 0, result.output
    out = _plain(result.output)
    assert "--resume" in out
    assert "--jd" in out
    assert "--company" in out
    assert "--notify" in out
    assert "--no-notify" in out


def test_ingest_help_shows_required_flags() -> None:
    result = CliRunner().invoke(app, ["ingest", "--help"])
    assert result.exit_code == 0, result.output
    assert "--resume" in _plain(result.output)


def test_tailor_missing_required_flag_fails() -> None:
    result = CliRunner().invoke(app, ["tailor"])
    assert result.exit_code != 0
    out = _plain(result.output).lower()
    assert "missing option" in out or "required" in out


def test_tailor_nonexistent_resume_fails_arg_validation() -> None:
    result = CliRunner().invoke(
        app, ["tailor", "--resume", "/no/such/file.pdf", "--jd", "/no/such/jd.txt"]
    )
    assert result.exit_code != 0
    out = _plain(result.output).lower()
    assert "does not exist" in out or "invalid" in out
