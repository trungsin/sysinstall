"""Tests for global Typer flags propagation to subcommands via merge_global_flags."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from sysinstall.cli import app, merge_global_flags

# ---------------------------------------------------------------------------
# merge_global_flags unit tests (pure logic, no CLI invocation)
# ---------------------------------------------------------------------------


class TestMergeGlobalFlags:
    def _make_ctx(self, obj: dict | None = None) -> MagicMock:
        ctx = MagicMock()
        ctx.obj = obj or {}
        ctx.parent = None
        return ctx

    def test_all_false_by_default(self) -> None:
        ctx = self._make_ctx()
        merged = merge_global_flags(ctx)
        assert merged["confirm"] is False
        assert merged["dry_run"] is False
        assert merged["allow_fixed_disk"] is False
        assert merged["force_encrypted"] is False
        assert merged["auto_unmount"] is False

    def test_global_flag_propagates(self) -> None:
        ctx = self._make_ctx({"confirm": True, "dry_run": False,
                               "allow_fixed_disk": False, "force_encrypted": False,
                               "auto_unmount": False})
        merged = merge_global_flags(ctx)
        assert merged["confirm"] is True

    def test_local_flag_overrides(self) -> None:
        ctx = self._make_ctx()
        merged = merge_global_flags(ctx, allow_fixed_disk=True)
        assert merged["allow_fixed_disk"] is True

    def test_or_semantics_both_true(self) -> None:
        ctx = self._make_ctx({"confirm": True, "dry_run": False,
                               "allow_fixed_disk": False, "force_encrypted": False,
                               "auto_unmount": False})
        merged = merge_global_flags(ctx, confirm=True)
        assert merged["confirm"] is True

    def test_or_semantics_global_true_local_false(self) -> None:
        ctx = self._make_ctx({"dry_run": True, "confirm": False,
                               "allow_fixed_disk": False, "force_encrypted": False,
                               "auto_unmount": False})
        merged = merge_global_flags(ctx, dry_run=False)
        assert merged["dry_run"] is True

    def test_walks_up_parent_chain(self) -> None:
        parent = MagicMock()
        parent.obj = {"confirm": True, "dry_run": False,
                      "allow_fixed_disk": False, "force_encrypted": False,
                      "auto_unmount": False}
        parent.parent = None
        child = MagicMock()
        child.obj = None   # child has no obj — walks to parent
        child.parent = parent
        merged = merge_global_flags(child)
        assert merged["confirm"] is True


# ---------------------------------------------------------------------------
# CLI integration: --help shows global flags
# ---------------------------------------------------------------------------


class TestGlobalFlagsHelp:
    def test_help_shows_confirm_flag(self) -> None:
        runner = CliRunner()
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "--confirm" in result.output

    def test_help_shows_dry_run_flag(self) -> None:
        runner = CliRunner()
        result = runner.invoke(app, ["--help"])
        assert "--dry-run" in result.output

    def test_help_shows_allow_fixed_disk_flag(self) -> None:
        runner = CliRunner()
        result = runner.invoke(app, ["--help"])
        assert "--allow-fixed-disk" in result.output

    def test_help_shows_force_encrypted_flag(self) -> None:
        runner = CliRunner()
        result = runner.invoke(app, ["--help"])
        assert "--force-encrypted" in result.output

    def test_help_shows_auto_unmount_flag(self) -> None:
        runner = CliRunner()
        result = runner.invoke(app, ["--help"])
        assert "--auto-unmount" in result.output


# ---------------------------------------------------------------------------
# System-disk uncircumventable via CLI
# ---------------------------------------------------------------------------


class TestSystemDiskUncircumventable:
    """Verify system disk is refused even when every override global flag is set."""

    def _make_system_disk(self) -> MagicMock:
        from sysinstall.disks.base import Disk
        return Disk(
            id="sata:SystemDisk:SN000",
            path="/dev/sda",
            size_bytes=500 * 1024**3,
            model="SystemDisk",
            serial="SN000",
            bus="sata",
            is_removable=False,
            is_system=True,
            partitions=(),
        )

    def test_usb_create_refuses_system_disk_with_all_overrides(self) -> None:
        """System disk must be refused even with every override flag set.

        Patching sys.platform to linux so usb create does not exit early for macOS.
        The system-disk SafetyError is the only refusal path we assert here.
        """
        runner = CliRunner()
        disk = self._make_system_disk()

        with (
            patch("sysinstall.cli.usb.sys") as mock_sys,
            patch("sysinstall.cli.usb._resolve_disk", return_value=disk),
            patch("sysinstall.safety.gates.detect_encryption", return_value="none"),
        ):
            mock_sys.platform = "linux"
            result = runner.invoke(
                app,
                [
                    "--confirm",
                    "--allow-fixed-disk",
                    "--force-encrypted",
                    "--auto-unmount",
                    "--dry-run",
                    "usb", "create",
                    "--device", "/dev/sda",
                    "--confirm",
                    "--allow-fixed-disk",
                    "--force-encrypted",
                    "--auto-unmount",
                    "--dry-run",
                ],
            )
        # Must exit 2 — system disk is uncircumventable
        assert result.exit_code == 2
        assert "system" in result.output.lower()
