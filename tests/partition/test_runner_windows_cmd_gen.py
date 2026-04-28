"""Assert PowerShell script lines for the Windows runner command builder."""

from __future__ import annotations

import pytest

from sysinstall.disks.base import Disk
from sysinstall.partition.layout import DualBootLayout
from sysinstall.partition.planner import plan
from sysinstall.partition.runner_windows import _extract_disk_number, commands

_GB = 1024 * 1024 * 1024


def _make_disk(size_bytes: int, path: str = r"\\.\PhysicalDrive1") -> Disk:
    return Disk(
        id="test:disk:0",
        path=path,
        size_bytes=size_bytes,
        model="TestDisk",
        serial="SN123",
        bus="sata",
        is_removable=False,
        is_system=False,
        partitions=(),
    )


def _canonical_plan(path: str = r"\\.\PhysicalDrive1"):
    disk = _make_disk(500 * _GB, path)
    layout = DualBootLayout(windows_size_gb=100, swap_size_gb=4)
    return plan(disk, layout)


class TestExtractDiskNumber:
    def test_drive1(self) -> None:
        assert _extract_disk_number(r"\\.\PhysicalDrive1") == 1

    def test_drive0(self) -> None:
        assert _extract_disk_number(r"\\.\PhysicalDrive0") == 0

    def test_drive99(self) -> None:
        assert _extract_disk_number(r"\\.\PhysicalDrive99") == 99

    def test_invalid_path_raises(self) -> None:
        with pytest.raises(ValueError):
            _extract_disk_number("/dev/sdb")


class TestClearAndInitialize:
    def setup_method(self) -> None:
        self.lines = commands(_canonical_plan())

    def test_clear_disk_first(self) -> None:
        assert self.lines[0] == "Clear-Disk -Number 1 -RemoveData -Confirm:$false"

    def test_initialize_disk_second(self) -> None:
        assert self.lines[1] == "Initialize-Disk -Number 1 -PartitionStyle GPT"


class TestNewPartitionLines:
    def setup_method(self) -> None:
        self.lines = commands(_canonical_plan())
        self.new_part_lines = [l for l in self.lines if l.startswith("New-Partition")]

    def test_five_new_partition_lines(self) -> None:
        assert len(self.new_part_lines) == 5

    def test_esp_guid_present(self) -> None:
        esp_line = self.new_part_lines[0]
        assert "C12A7328-F81F-11D2-BA4B-00A0C93EC93B" in esp_line

    def test_msr_guid_present(self) -> None:
        msr_line = self.new_part_lines[1]
        assert "E3C9E316-0B5C-4DB8-817D-F92DF00215AE" in msr_line

    def test_windows_guid_present(self) -> None:
        win_line = self.new_part_lines[2]
        assert "EBD0A0A2-B9E5-4433-87C0-68B6B72699C7" in win_line

    def test_linux_fs_guid_present(self) -> None:
        linux_line = self.new_part_lines[3]
        assert "0FC63DAF-8483-4772-8E79-3D69D8477DE4" in linux_line

    def test_swap_guid_present(self) -> None:
        swap_line = self.new_part_lines[4]
        assert "0657FD6D-A4AB-43C4-84E5-0933C84B4F4F" in swap_line

    def test_size_in_bytes_for_esp(self) -> None:
        # 512 MiB = 512 * 1024 * 1024 bytes
        expected_bytes = 512 * 1024 * 1024
        esp_line = self.new_part_lines[0]
        assert f"-Size {expected_bytes}" in esp_line

    def test_guid_wrapped_in_braces(self) -> None:
        # PowerShell requires GptType in the form '{GUID}'
        esp_line = self.new_part_lines[0]
        assert "-GptType '{C12A7328-F81F-11D2-BA4B-00A0C93EC93B}'" in esp_line


class TestFormatVolumeLines:
    def setup_method(self) -> None:
        self.lines = commands(_canonical_plan())
        self.format_lines = [l for l in self.lines if "Format-Volume" in l]

    def test_two_format_volume_lines(self) -> None:
        # ESP (FAT32) + Windows (NTFS)
        assert len(self.format_lines) == 2

    def test_esp_formatted_fat32(self) -> None:
        fat32_line = next((l for l in self.format_lines if "FAT32" in l), None)
        assert fat32_line is not None
        assert "EFI" in fat32_line or "PartitionNumber 1" in fat32_line

    def test_windows_formatted_ntfs(self) -> None:
        ntfs_line = next((l for l in self.format_lines if "NTFS" in l), None)
        assert ntfs_line is not None


class TestExt4SwapNotFormatted:
    """Ubuntu root and swap partitions must NOT have Format-Volume lines."""

    def test_no_ext4_format(self) -> None:
        lines = commands(_canonical_plan())
        assert not any("ext4" in l.lower() for l in lines)

    def test_no_swap_format(self) -> None:
        lines = commands(_canonical_plan())
        # swap partition should not have Format-Volume
        format_lines = [l for l in lines if "Format-Volume" in l]
        assert not any("swap" in l.lower() for l in format_lines)


class TestNoSwapPlan:
    def test_four_new_partition_lines(self) -> None:
        disk = _make_disk(500 * _GB)
        layout = DualBootLayout(windows_size_gb=100, swap_size_gb=0)
        p = plan(disk, layout)
        lines = commands(p)
        new_part_lines = [l for l in lines if l.startswith("New-Partition")]
        assert len(new_part_lines) == 4
