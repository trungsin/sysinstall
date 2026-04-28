"""Tests that repair() and CLI commands exit 2 on non-Linux hosts.

These tests run on macOS (darwin) in CI, verifying the host gate works.
"""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from sysinstall.boot.types import RepairPlan, UnsupportedHostError
from sysinstall.disks.base import Partition


def _make_partition(part_id: str = "/dev/sda1") -> Partition:
    return Partition(
        id=part_id,
        fs_type="ext4",
        size_bytes=10 * 1024**3,
        mountpoints=(),
        label="ubuntu",
    )


def _make_plan() -> RepairPlan:
    return RepairPlan(
        firmware="uefi",
        efi_partition=_make_partition("/dev/sda1"),
        root_partition=_make_partition("/dev/sda3"),
        enable_os_prober=True,
        set_boot_order_first=True,
    )


# ---------------------------------------------------------------------------
# Module-level repair() gate
# ---------------------------------------------------------------------------


def test_repair_raises_unsupported_on_darwin() -> None:
    """repair() raises UnsupportedHostError on non-Linux hosts."""
    with patch.object(sys, "platform", "darwin"):
        from sysinstall.boot import repair

        with pytest.raises(UnsupportedHostError, match="Ubuntu live USB"):
            repair(_make_plan(), dry_run=True)


def test_repair_raises_unsupported_on_win32() -> None:
    with patch.object(sys, "platform", "win32"):
        from sysinstall.boot import repair

        with pytest.raises(UnsupportedHostError, match="Ubuntu live USB"):
            repair(_make_plan(), dry_run=True)


# ---------------------------------------------------------------------------
# CLI host gate via typer test runner
# ---------------------------------------------------------------------------


def test_cli_detect_exits_2_on_darwin() -> None:
    from typer.testing import CliRunner

    from sysinstall.cli.boot import app

    runner = CliRunner()
    with patch.object(sys, "platform", "darwin"):
        result = runner.invoke(app, ["detect"])
    assert result.exit_code == 2
    assert "Ubuntu live USB" in (result.output + (result.stderr or ""))


def test_cli_repair_exits_2_on_darwin() -> None:
    from typer.testing import CliRunner

    from sysinstall.cli.boot import app

    runner = CliRunner()
    with patch.object(sys, "platform", "darwin"):
        result = runner.invoke(
            app,
            ["repair", "--ubuntu-root", "/dev/sda3", "--efi", "/dev/sda1", "--confirm", "--dry-run"],
        )
    assert result.exit_code == 2
    assert "Ubuntu live USB" in (result.output + (result.stderr or ""))
