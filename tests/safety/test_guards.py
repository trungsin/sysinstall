"""Tests for safety guards: refuse_if_system, refuse_if_fixed, validate_disk_path."""

from __future__ import annotations

from unittest.mock import patch

import pytest
import typer

from sysinstall.disks.base import Disk
from sysinstall.safety.guards import (
    confirm_destructive,
    refuse_if_fixed,
    refuse_if_system,
    validate_disk_path,
)


def _make_disk(
    *,
    is_system: bool = False,
    is_removable: bool = True,
    path: str = "/dev/sdb",
    size_bytes: int = 16 * 1024 ** 3,
) -> Disk:
    return Disk(
        id="usb:TestModel:SN999",
        path=path,
        size_bytes=size_bytes,
        model="TestModel",
        serial="SN999",
        bus="usb",
        is_removable=is_removable,
        is_system=is_system,
        partitions=(),
    )


# ---------------------------------------------------------------------------
# validate_disk_path
# ---------------------------------------------------------------------------

class TestValidateDiskPath:
    @pytest.mark.parametrize("path", [
        "/dev/sda",
        "/dev/sdb",
        "/dev/sdz",
        "/dev/nvme0n1",
        "/dev/nvme1n2",
        "/dev/disk0",
        "/dev/disk12",
        r"\\.\PhysicalDrive0",
        r"\\.\PhysicalDrive10",
    ])
    def test_valid_paths_pass(self, path: str):
        validate_disk_path(path)  # must not raise

    @pytest.mark.parametrize("path", [
        "/dev/sda1",          # partition, not whole disk
        "/dev/vda",           # virtio (not in allowlist)
        "/dev/loop0",         # loop device
        "/tmp/evil; rm -rf",  # injection attempt
        "",
        "/dev/",
        "PhysicalDrive0",     # missing prefix
        "/dev/nvme0",         # missing n\d suffix
    ])
    def test_invalid_paths_raise(self, path: str):
        with pytest.raises(typer.BadParameter):
            validate_disk_path(path)


# ---------------------------------------------------------------------------
# refuse_if_system
# ---------------------------------------------------------------------------

class TestRefuseIfSystem:
    def test_system_disk_raises_exit_2(self):
        disk = _make_disk(is_system=True)
        with pytest.raises(typer.Exit) as exc_info:
            refuse_if_system(disk)
        assert exc_info.value.exit_code == 2

    def test_non_system_disk_passes(self):
        disk = _make_disk(is_system=False)
        refuse_if_system(disk)  # must not raise

    def test_error_output_mentions_system(self, capsys):
        disk = _make_disk(is_system=True)
        with pytest.raises(typer.Exit):
            refuse_if_system(disk)
        captured = capsys.readouterr()
        assert "system" in (captured.out + captured.err).lower()


# ---------------------------------------------------------------------------
# refuse_if_fixed
# ---------------------------------------------------------------------------

class TestRefuseIfFixed:
    def test_fixed_disk_without_flag_raises_exit_2(self):
        disk = _make_disk(is_removable=False)
        with pytest.raises(typer.Exit) as exc_info:
            refuse_if_fixed(disk, allow_fixed=False)
        assert exc_info.value.exit_code == 2

    def test_fixed_disk_with_flag_passes(self):
        disk = _make_disk(is_removable=False)
        refuse_if_fixed(disk, allow_fixed=True)  # must not raise

    def test_removable_disk_always_passes(self):
        disk = _make_disk(is_removable=True)
        refuse_if_fixed(disk, allow_fixed=False)  # must not raise


# ---------------------------------------------------------------------------
# confirm_destructive
# ---------------------------------------------------------------------------

class TestConfirmDestructive:
    def test_confirm_flag_skips_prompt(self, capsys):
        disk = _make_disk()
        confirm_destructive(disk, "test action", confirmed=True)
        captured = capsys.readouterr()
        assert "WARNING" in (captured.out + captured.err)

    def test_interactive_yes_proceeds(self):
        disk = _make_disk()
        with patch("typer.prompt", return_value="yes"):
            confirm_destructive(disk, "test action", confirmed=False)

    def test_interactive_no_aborts(self):
        disk = _make_disk()
        with patch("typer.prompt", return_value="no"), pytest.raises(typer.Abort):
            confirm_destructive(disk, "test action", confirmed=False)

    def test_interactive_default_aborts(self):
        disk = _make_disk()
        with patch("typer.prompt", return_value=""), pytest.raises(typer.Abort):
            confirm_destructive(disk, "test action", confirmed=False)

    def test_output_contains_disk_info(self, capsys):
        disk = _make_disk()
        confirm_destructive(disk, "test action", confirmed=True)
        out = capsys.readouterr().out
        assert disk.path in out
        assert disk.model in out
