"""Smoke tests — verify CLI entrypoint responds correctly."""

from typer.testing import CliRunner

from sysinstall import __version__
from sysinstall.cli import app

runner = CliRunner()


def test_version_exits_zero() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0


def test_version_prints_version_string() -> None:
    result = runner.invoke(app, ["--version"])
    assert __version__ in result.output


def test_help_lists_subgroups() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for group in ("disk", "usb", "iso", "boot"):
        assert group in result.output
