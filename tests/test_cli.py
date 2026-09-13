from __future__ import annotations

from typer.testing import CliRunner

from lens_core.cli import app

runner = CliRunner()


def test_help_lists_all_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("ingest", "eval", "redteam", "label", "ci", "serve"):
        assert cmd in result.output


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0 and result.output.startswith("lens ")


def test_commands_require_their_options() -> None:
    for cmd in ("eval", "redteam", "label", "ci"):
        result = runner.invoke(app, [cmd])
        assert result.exit_code == 2, cmd  # typer usage error: missing required options
