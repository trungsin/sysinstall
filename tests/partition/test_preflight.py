"""Tests for preflight encryption detection with mocked subprocess."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from sysinstall.disks.base import Disk, Partition
from sysinstall.partition.preflight import (
    EncryptionStatus,
    _check_linux,
    _check_macos,
    _check_windows,
    unmount_all,
)


def _make_disk(path: str = "/dev/sdb", partitions: tuple[Partition, ...] = ()) -> Disk:
    return Disk(
        id="test:disk:0",
        path=path,
        size_bytes=500 * 1024 * 1024 * 1024,
        model="TestDisk",
        serial="SN123",
        bus="sata",
        is_removable=False,
        is_system=False,
        partitions=partitions,
    )


def _make_partition(part_id: str, mountpoints: tuple[str, ...] = ()) -> Partition:
    return Partition(
        id=part_id,
        fs_type="ext4",
        size_bytes=1024 * 1024 * 1024,
        mountpoints=mountpoints,
        label=None,
    )


class TestLinuxEncryptionCheck:
    def test_no_partitions_returns_none(self) -> None:
        disk = _make_disk()
        result = _check_linux(disk)
        assert result == EncryptionStatus.none

    def test_cryptsetup_not_available_returns_unknown(self) -> None:
        disk = _make_disk(partitions=(_make_partition("/dev/sdb1"),))
        with patch(
            "sysinstall.partition.preflight._tool_available", return_value=False
        ):
            result = _check_linux(disk)
        assert result == EncryptionStatus.unknown

    def test_all_partitions_encrypted_returns_full(self) -> None:
        disk = _make_disk(
            partitions=(
                _make_partition("/dev/sdb1"),
                _make_partition("/dev/sdb2"),
            )
        )
        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("sysinstall.partition.preflight._tool_available", return_value=True), \
             patch("subprocess.run", return_value=mock_result):
            result = _check_linux(disk)

        assert result == EncryptionStatus.full

    def test_no_partitions_encrypted_returns_none_status(self) -> None:
        disk = _make_disk(
            partitions=(
                _make_partition("/dev/sdb1"),
                _make_partition("/dev/sdb2"),
            )
        )
        mock_result = MagicMock()
        mock_result.returncode = 1  # not LUKS

        with patch("sysinstall.partition.preflight._tool_available", return_value=True), \
             patch("subprocess.run", return_value=mock_result):
            result = _check_linux(disk)

        assert result == EncryptionStatus.none

    def test_partial_encryption_returns_partial(self) -> None:
        disk = _make_disk(
            partitions=(
                _make_partition("/dev/sdb1"),
                _make_partition("/dev/sdb2"),
            )
        )
        # First call returns 0 (encrypted), second returns 1 (clear)
        results = [MagicMock(returncode=0), MagicMock(returncode=1)]

        with patch("sysinstall.partition.preflight._tool_available", return_value=True), \
             patch("subprocess.run", side_effect=results):
            result = _check_linux(disk)

        assert result == EncryptionStatus.partial

    def test_timeout_returns_unknown(self) -> None:
        disk = _make_disk(partitions=(_make_partition("/dev/sdb1"),))

        with patch("sysinstall.partition.preflight._tool_available", return_value=True), \
             patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cryptsetup", 30)):
            result = _check_linux(disk)

        assert result == EncryptionStatus.unknown


class TestWindowsEncryptionCheck:
    def test_bitlocker_on_returns_full(self) -> None:
        disk = _make_disk(path=r"\\.\PhysicalDrive1")
        mock_result = MagicMock()
        mock_result.stdout = "On\nOn\n"

        with patch("subprocess.run", return_value=mock_result):
            result = _check_windows(disk)

        assert result == EncryptionStatus.full

    def test_bitlocker_off_returns_none(self) -> None:
        disk = _make_disk(path=r"\\.\PhysicalDrive1")
        mock_result = MagicMock()
        mock_result.stdout = "Off\nOff\n"

        with patch("subprocess.run", return_value=mock_result):
            result = _check_windows(disk)

        assert result == EncryptionStatus.none

    def test_mixed_returns_partial(self) -> None:
        disk = _make_disk(path=r"\\.\PhysicalDrive1")
        mock_result = MagicMock()
        mock_result.stdout = "On\nOff\n"

        with patch("subprocess.run", return_value=mock_result):
            result = _check_windows(disk)

        assert result == EncryptionStatus.partial

    def test_empty_output_returns_none(self) -> None:
        disk = _make_disk(path=r"\\.\PhysicalDrive1")
        mock_result = MagicMock()
        mock_result.stdout = ""

        with patch("subprocess.run", return_value=mock_result):
            result = _check_windows(disk)

        assert result == EncryptionStatus.none

    def test_powershell_not_found_returns_unknown(self) -> None:
        disk = _make_disk(path=r"\\.\PhysicalDrive1")

        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = _check_windows(disk)

        assert result == EncryptionStatus.unknown


class TestMacosEncryptionCheck:
    def test_filevault_on_returns_full(self) -> None:
        disk = _make_disk(path="/dev/disk2")
        fde_result = MagicMock()
        fde_result.stdout = "FileVault is On.\n"
        apfs_result = MagicMock()
        apfs_result.stdout = ""

        with patch("subprocess.run", side_effect=[fde_result, apfs_result]):
            result = _check_macos(disk)

        assert result == EncryptionStatus.full

    def test_filevault_off_returns_none(self) -> None:
        disk = _make_disk(path="/dev/disk2")
        fde_result = MagicMock()
        fde_result.stdout = "FileVault is Off.\n"
        apfs_result = MagicMock()
        apfs_result.stdout = ""

        with patch("subprocess.run", side_effect=[fde_result, apfs_result]):
            result = _check_macos(disk)

        assert result == EncryptionStatus.none

    def test_fdesetup_not_found_returns_unknown(self) -> None:
        disk = _make_disk(path="/dev/disk2")

        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = _check_macos(disk)

        assert result == EncryptionStatus.unknown


class TestUnmountAll:
    def test_linux_calls_umount_per_mountpoint(self) -> None:
        part = _make_partition("/dev/sdb1", mountpoints=("/mnt/data",))
        disk = _make_disk(partitions=(part,))
        mock_result = MagicMock()

        with patch("sys.platform", "linux"), \
             patch("subprocess.run", return_value=mock_result) as mock_run:
            warnings = unmount_all(disk)

        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert call_args == ["umount", "/mnt/data"]
        assert warnings == []

    def test_no_mountpoints_no_calls(self) -> None:
        disk = _make_disk(partitions=(_make_partition("/dev/sdb1"),))

        with patch("sys.platform", "linux"), \
             patch("subprocess.run") as mock_run:
            unmount_all(disk)

        mock_run.assert_not_called()

    def test_macos_calls_diskutil_unmount(self) -> None:
        disk = _make_disk(path="/dev/disk2")
        mock_result = MagicMock()

        with patch("sys.platform", "darwin"), \
             patch("subprocess.run", return_value=mock_result) as mock_run:
            warnings = unmount_all(disk)

        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert call_args[:3] == ["diskutil", "unmountDisk", "force"]
        assert warnings == []
