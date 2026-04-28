"""Tests for safety gate pipeline: each gate in isolation + pipeline ordering.

Key invariant: SystemDiskGate is NEVER circumventable regardless of flags.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from sysinstall.disks.base import Disk, Partition
from sysinstall.safety.errors import SafetyError
from sysinstall.safety.gates import (
    EncryptionGate,
    FixedDiskGate,
    Gate,
    GateOptions,
    MountedGate,
    SystemDiskGate,
    check_destructive,
    detect_encryption,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_disk(
    *,
    is_system: bool = False,
    is_removable: bool = True,
    path: str = "/dev/sdb",
    partitions: tuple[Partition, ...] = (),
) -> Disk:
    return Disk(
        id="usb:TestModel:SN999",
        path=path,
        size_bytes=16 * 1024**3,
        model="TestModel",
        serial="SN999",
        bus="usb",
        is_removable=is_removable,
        is_system=is_system,
        partitions=partitions,
    )


def _make_partition(mp: str = "") -> Partition:
    return Partition(
        id="/dev/sdb1",
        fs_type="ext4",
        size_bytes=8 * 1024**3,
        mountpoints=(mp,) if mp else (),
        label=None,
    )


def _opts(**kwargs: bool) -> GateOptions:
    return GateOptions(**kwargs)


# ---------------------------------------------------------------------------
# Gate protocol conformance
# ---------------------------------------------------------------------------


class TestGateProtocol:
    def test_all_gate_classes_satisfy_protocol(self) -> None:
        for cls in [SystemDiskGate, EncryptionGate, FixedDiskGate, MountedGate]:
            assert isinstance(cls(), Gate)


# ---------------------------------------------------------------------------
# SystemDiskGate
# ---------------------------------------------------------------------------


class TestSystemDiskGate:
    def test_system_disk_raises_safety_error(self) -> None:
        gate = SystemDiskGate()
        disk = _make_disk(is_system=True)
        with pytest.raises(SafetyError) as exc_info:
            gate.check(disk, "test_op", _opts())
        err = exc_info.value
        assert err.category == "system_disk"
        assert err.overridable is False

    def test_non_system_disk_passes(self) -> None:
        gate = SystemDiskGate()
        disk = _make_disk(is_system=False)
        gate.check(disk, "test_op", _opts())  # must not raise

    def test_system_disk_uncircumventable_with_all_overrides(self) -> None:
        """System disk must be refused even with every override flag set."""
        gate = SystemDiskGate()
        disk = _make_disk(is_system=True)
        opts = _opts(
            allow_fixed=True,
            force_encrypted=True,
            auto_unmount=True,
            confirmed=True,
            dry_run=True,
        )
        with pytest.raises(SafetyError) as exc_info:
            gate.check(disk, "test_op", opts)
        assert exc_info.value.category == "system_disk"
        assert exc_info.value.overridable is False

    def test_error_contains_disk_path(self) -> None:
        gate = SystemDiskGate()
        disk = _make_disk(is_system=True, path="/dev/sda")
        with pytest.raises(SafetyError) as exc_info:
            gate.check(disk, "test_op", _opts())
        assert "/dev/sda" in str(exc_info.value)


# ---------------------------------------------------------------------------
# EncryptionGate
# ---------------------------------------------------------------------------


class TestEncryptionGate:
    def test_encrypted_disk_raises(self) -> None:
        gate = EncryptionGate()
        disk = _make_disk()
        with patch("sysinstall.safety.gates.detect_encryption", return_value="full"):
            with pytest.raises(SafetyError) as exc_info:
                gate.check(disk, "test_op", _opts())
        assert exc_info.value.category == "encrypted"
        assert exc_info.value.overridable is True

    def test_partial_encryption_raises(self) -> None:
        gate = EncryptionGate()
        disk = _make_disk()
        with patch("sysinstall.safety.gates.detect_encryption", return_value="partial"):
            with pytest.raises(SafetyError) as exc_info:
                gate.check(disk, "test_op", _opts())
        assert exc_info.value.category == "encrypted"

    def test_force_encrypted_allows_pass(self) -> None:
        gate = EncryptionGate()
        disk = _make_disk()
        with patch("sysinstall.safety.gates.detect_encryption", return_value="full"):
            gate.check(disk, "test_op", _opts(force_encrypted=True))  # must not raise

    def test_unencrypted_disk_passes(self) -> None:
        gate = EncryptionGate()
        disk = _make_disk()
        with patch("sysinstall.safety.gates.detect_encryption", return_value="none"):
            gate.check(disk, "test_op", _opts())  # must not raise

    def test_unknown_encryption_passes(self) -> None:
        """Unknown encryption status should pass (not all platforms support detection)."""
        gate = EncryptionGate()
        disk = _make_disk()
        with patch("sysinstall.safety.gates.detect_encryption", return_value="unknown"):
            gate.check(disk, "test_op", _opts())  # must not raise


# ---------------------------------------------------------------------------
# FixedDiskGate
# ---------------------------------------------------------------------------


class TestFixedDiskGate:
    def test_fixed_disk_without_flag_raises(self) -> None:
        gate = FixedDiskGate()
        disk = _make_disk(is_removable=False)
        with pytest.raises(SafetyError) as exc_info:
            gate.check(disk, "test_op", _opts())
        assert exc_info.value.category == "fixed_disk"
        assert exc_info.value.overridable is True

    def test_fixed_disk_with_allow_fixed_passes(self) -> None:
        gate = FixedDiskGate()
        disk = _make_disk(is_removable=False)
        gate.check(disk, "test_op", _opts(allow_fixed=True))  # must not raise

    def test_removable_disk_always_passes(self) -> None:
        gate = FixedDiskGate()
        disk = _make_disk(is_removable=True)
        gate.check(disk, "test_op", _opts())  # must not raise


# ---------------------------------------------------------------------------
# MountedGate
# ---------------------------------------------------------------------------


class TestMountedGate:
    def test_mounted_partition_raises(self) -> None:
        gate = MountedGate()
        part = _make_partition(mp="/mnt/usb")
        disk = _make_disk(partitions=(part,))
        with pytest.raises(SafetyError) as exc_info:
            gate.check(disk, "test_op", _opts())
        assert exc_info.value.category == "mounted"
        assert exc_info.value.overridable is True

    def test_unmounted_disk_passes(self) -> None:
        gate = MountedGate()
        part = _make_partition(mp="")
        disk = _make_disk(partitions=(part,))
        gate.check(disk, "test_op", _opts())  # must not raise

    def test_no_partitions_passes(self) -> None:
        gate = MountedGate()
        disk = _make_disk(partitions=())
        gate.check(disk, "test_op", _opts())  # must not raise

    def test_auto_unmount_calls_unmount_all(self) -> None:
        gate = MountedGate()
        part = _make_partition(mp="/mnt/usb")
        disk = _make_disk(partitions=(part,))
        # After unmount, disk has no more mounted partitions (simulate by
        # patching _mounted_partitions to return [] on second call).
        call_count = 0

        def _fake_mounted(d: Disk) -> list[tuple[str, str]]:
            nonlocal call_count
            call_count += 1
            return [("/dev/sdb1", "/mnt/usb")] if call_count == 1 else []

        with (
            patch("sysinstall.safety.gates._mounted_partitions", side_effect=_fake_mounted),
            patch("sysinstall.safety.gates.unmount_all", return_value=[]) as mock_unmount,
        ):
            gate.check(disk, "test_op", _opts(auto_unmount=True))
        mock_unmount.assert_called_once_with(disk)

    def test_auto_unmount_raises_when_unmount_fails(self) -> None:
        gate = MountedGate()
        part = _make_partition(mp="/mnt/usb")
        disk = _make_disk(partitions=(part,))

        with (
            patch(
                "sysinstall.safety.gates._mounted_partitions",
                return_value=[("/dev/sdb1", "/mnt/usb")],
            ),
            patch("sysinstall.safety.gates.unmount_all", return_value=["umount failed"]),
        ):
            with pytest.raises(SafetyError) as exc_info:
                gate.check(disk, "test_op", _opts(auto_unmount=True))
        assert exc_info.value.category == "mounted"


# ---------------------------------------------------------------------------
# Pipeline ordering: check_destructive
# ---------------------------------------------------------------------------


class TestCheckDestructivePipeline:
    def test_system_disk_refused_before_any_other_gate(self) -> None:
        """SystemDiskGate fires first — EncryptionGate must not even run."""
        disk = _make_disk(is_system=True)
        enc_mock = MagicMock()
        with patch("sysinstall.safety.gates._GATES", [SystemDiskGate(), enc_mock]):
            with pytest.raises(SafetyError) as exc_info:
                check_destructive(disk, "test_op")
        assert exc_info.value.category == "system_disk"
        enc_mock.check.assert_not_called()

    def test_pipeline_passes_for_safe_disk(self) -> None:
        disk = _make_disk(is_removable=True, is_system=False)
        with patch("sysinstall.safety.gates.detect_encryption", return_value="none"):
            check_destructive(disk, "test_op")  # must not raise

    def test_all_override_flags_still_refuse_system_disk(self) -> None:
        """System disk must be refused regardless of every override flag."""
        disk = _make_disk(is_system=True)
        with pytest.raises(SafetyError) as exc_info:
            check_destructive(
                disk,
                "test_op",
                allow_fixed=True,
                force_encrypted=True,
                auto_unmount=True,
                confirmed=True,
                dry_run=True,
            )
        assert exc_info.value.category == "system_disk"

    def test_fixed_gate_skipped_when_allow_fixed(self) -> None:
        disk = _make_disk(is_removable=False, is_system=False)
        with patch("sysinstall.safety.gates.detect_encryption", return_value="none"):
            # must not raise because allow_fixed=True skips FixedDiskGate
            check_destructive(disk, "test_op", allow_fixed=True)

    def test_encryption_gate_skipped_with_force_encrypted(self) -> None:
        disk = _make_disk(is_system=False)
        with patch("sysinstall.safety.gates.detect_encryption", return_value="full"):
            # force_encrypted allows pass-through (warn only)
            check_destructive(disk, "test_op", force_encrypted=True)


# ---------------------------------------------------------------------------
# detect_encryption helper
# ---------------------------------------------------------------------------


class TestDetectEncryption:
    def test_returns_string_value(self) -> None:
        disk = _make_disk()
        with patch("sysinstall.safety.gates.sys") as mock_sys:
            mock_sys.platform = "linux"
            with patch("sysinstall.safety.gates._detect_encryption_linux", return_value="none"):
                result = detect_encryption(disk)
        assert result in ("full", "partial", "none", "unknown")

    def test_unknown_platform_returns_unknown(self) -> None:
        disk = _make_disk()
        import sys as real_sys
        original = real_sys.platform
        try:
            real_sys.platform = "freebsd"  # type: ignore[assignment]
            result = detect_encryption(disk)
        finally:
            real_sys.platform = original  # type: ignore[assignment]
        assert result == "unknown"
