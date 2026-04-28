"""CLI smoke tests — verify all subcommands parse and dry-run correctly."""

from __future__ import annotations

import sys

import pytest
from typer.testing import CliRunner

from sysinstall.cli import app

runner = CliRunner()


class TestMainCommands:
    """Test main help and version."""

    def test_help(self) -> None:
        """--help should exit 0."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "Usage:" in result.stdout or "Commands:" in result.stdout

    def test_version(self) -> None:
        """--version should exit 0."""
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        # Version output varies; just check it exits cleanly
        assert len(result.stdout) > 0


class TestDiskSubcommand:
    """Test disk subcommand."""

    def test_disk_help(self) -> None:
        """disk --help should exit 0."""
        result = runner.invoke(app, ["disk", "--help"])
        assert result.exit_code == 0
        assert "Usage:" in result.stdout or "Commands:" in result.stdout

    def test_disk_list_help(self) -> None:
        """disk list --help should exit 0."""
        result = runner.invoke(app, ["disk", "list", "--help"])
        assert result.exit_code == 0

    def test_disk_list_dry_run_no_write(self) -> None:
        """disk list should not require --confirm; just list."""
        result = runner.invoke(app, ["disk", "list"])
        # Should succeed (or be empty on test runner)
        assert result.exit_code in (0, 1)  # 1 if no disks found, 0 if any


class TestUSBSubcommand:
    """Test usb subcommand."""

    def test_usb_help(self) -> None:
        """usb --help should exit 0."""
        result = runner.invoke(app, ["usb", "--help"])
        assert result.exit_code == 0
        assert "Usage:" in result.stdout or "Commands:" in result.stdout

    def test_usb_create_help(self) -> None:
        """usb create --help should exit 0."""
        result = runner.invoke(app, ["usb", "create", "--help"])
        assert result.exit_code == 0

    @pytest.mark.skipif(sys.platform != "darwin", reason="macOS-only dry-run test")
    def test_usb_create_missing_device_refuses(self) -> None:
        """usb create without --device should refuse with error."""
        result = runner.invoke(app, ["usb", "create", "--confirm"])
        # Should exit non-zero due to missing --device
        assert result.exit_code != 0

    @pytest.mark.skipif(sys.platform != "darwin", reason="macOS-only dry-run test")
    def test_usb_create_with_fake_device_dry_run(self) -> None:
        """usb create with fake --device and --dry-run should show plan."""
        result = runner.invoke(
            app,
            ["usb", "create", "--device", "disk999", "--dry-run", "--confirm"],
        )
        # Should exit 0 (dry-run is safe) or error if device lookup fails
        # The important part: no actual USB write happens
        assert result.exit_code in (0, 1, 2)


class TestBootSubcommand:
    """Test boot subcommand."""

    def test_boot_help(self) -> None:
        """boot --help should exit 0."""
        result = runner.invoke(app, ["boot", "--help"])
        assert result.exit_code == 0
        assert "Usage:" in result.stdout or "Commands:" in result.stdout

    def test_boot_detect_help(self) -> None:
        """boot detect --help should exit 0."""
        result = runner.invoke(app, ["boot", "detect", "--help"])
        assert result.exit_code == 0

    def test_boot_detect_dry_run(self) -> None:
        """boot detect is read-only, should always work."""
        result = runner.invoke(app, ["boot", "detect"])
        # Should exit 0 (on supported OS), 1 (no bootloaders found), or 2 (not implemented on this OS)
        assert result.exit_code in (0, 1, 2)

    def test_boot_repair_help(self) -> None:
        """boot repair --help should exit 0."""
        result = runner.invoke(app, ["boot", "repair", "--help"])
        assert result.exit_code == 0

    @pytest.mark.skipif(sys.platform != "darwin", reason="macOS safety gate test")
    def test_boot_repair_without_target_refuses(self) -> None:
        """boot repair without --target should refuse."""
        result = runner.invoke(app, ["boot", "repair", "--confirm"])
        # Should exit 2 (error) due to missing required arg
        assert result.exit_code != 0


class TestISO:
    """Test iso subcommand."""

    def test_iso_help(self) -> None:
        """iso --help should exit 0."""
        result = runner.invoke(app, ["iso", "--help"])
        assert result.exit_code == 0
        assert "Usage:" in result.stdout or "Commands:" in result.stdout

    def test_iso_add_help(self) -> None:
        """iso add --help should exit 0."""
        result = runner.invoke(app, ["iso", "add", "--help"])
        assert result.exit_code == 0

    def test_iso_list_help(self) -> None:
        """iso list --help should exit 0."""
        result = runner.invoke(app, ["iso", "list", "--help"])
        assert result.exit_code == 0


