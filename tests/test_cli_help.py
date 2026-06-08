from __future__ import annotations

from typer.testing import CliRunner

from jobforge.cli import app


def test_top_level_help_lists_commands() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0, result.output
    assert "ingest" in result.output
    assert "tailor" in result.output


def test_tailor_help_shows_required_flags() -> None:
    result = CliRunner().invoke(app, ["tailor", "--help"])
    assert result.exit_code == 0, result.output
    assert "--resume" in result.output
    assert "--jd" in result.output
    assert "--company" in result.output
    assert "--notify" in result.output
    assert "--no-notify" in result.output


def test_ingest_help_shows_required_flags() -> None:
    result = CliRunner().invoke(app, ["ingest", "--help"])
    assert result.exit_code == 0, result.output
    assert "--resume" in result.output


def test_tailor_missing_required_flag_fails() -> None:
    result = CliRunner().invoke(app, ["tailor"])
    assert result.exit_code != 0
    assert "Missing option" in result.output or "required" in result.output.lower()


def test_tailor_nonexistent_resume_fails_arg_validation() -> None:
    result = CliRunner().invoke(
        app, ["tailor", "--resume", "/no/such/file.pdf", "--jd", "/no/such/jd.txt"]
    )
    assert result.exit_code != 0
    assert "does not exist" in result.output.lower() or "invalid" in result.output.lower()
