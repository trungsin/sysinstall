"""Assert exact diskutil + gpt arg lists for the macOS runner command builder."""

from __future__ import annotations

from sysinstall.disks.base import Disk
from sysinstall.partition.layout import DualBootLayout
from sysinstall.partition.planner import plan
from sysinstall.partition.runner_macos import commands

_GB = 1024 * 1024 * 1024


def _make_disk(size_bytes: int, path: str = "/dev/disk2") -> Disk:
    return Disk(
        id="test:disk:0",
        path=path,
        size_bytes=size_bytes,
        model="TestDisk",
        serial="SN123",
        bus="usb",
        is_removable=True,
        is_system=False,
        partitions=(),
    )


def _canonical_plan(path: str = "/dev/disk2"):
    disk = _make_disk(500 * _GB, path)
    layout = DualBootLayout(windows_size_gb=100, swap_size_gb=4)
    return plan(disk, layout)


class TestDiskutilCommands:
    def setup_method(self) -> None:
        self.cmds = commands(_canonical_plan())

    def test_first_cmd_is_unmount(self) -> None:
        assert self.cmds[0] == ["diskutil", "unmountDisk", "force", "/dev/disk2"]

    def test_second_cmd_is_erase(self) -> None:
        assert self.cmds[1] == ["diskutil", "eraseDisk", "free", "None", "/dev/disk2"]

    def test_five_gpt_add_commands(self) -> None:
        gpt_cmds = [c for c in self.cmds if c[0] == "gpt" and c[1] == "add"]
        assert len(gpt_cmds) == 5

    def test_gpt_add_esp_structure(self) -> None:
        gpt_cmds = [c for c in self.cmds if c[0] == "gpt" and c[1] == "add"]
        esp_cmd = gpt_cmds[0]
        assert "-i" in esp_cmd
        assert "1" in esp_cmd
        assert "-b" in esp_cmd
        assert "-s" in esp_cmd
        assert "-t" in esp_cmd
        # ESP GUID in lowercase (BSD gpt convention)
        assert "c12a7328-f81f-11d2-ba4b-00a0c93ec93b" in esp_cmd
        assert "/dev/disk2" in esp_cmd

    def test_gpt_add_windows_guid(self) -> None:
        gpt_cmds = [c for c in self.cmds if c[0] == "gpt" and c[1] == "add"]
        win_cmd = gpt_cmds[2]  # index 2 = partition 3
        assert "ebd0a0a2-b9e5-4433-87c0-68b6b72699c7" in win_cmd

    def test_gpt_add_linux_fs_guid(self) -> None:
        gpt_cmds = [c for c in self.cmds if c[0] == "gpt" and c[1] == "add"]
        linux_cmd = gpt_cmds[3]
        assert "0fc63daf-8483-4772-8e79-3d69d8477de4" in linux_cmd

    def test_gpt_add_swap_guid(self) -> None:
        gpt_cmds = [c for c in self.cmds if c[0] == "gpt" and c[1] == "add"]
        swap_cmd = gpt_cmds[4]
        assert "0657fd6d-a4ab-43c4-84e5-0933c84b4f4f" in swap_cmd


class TestNewfsMsdosForEsp:
    def test_newfs_msdos_present(self) -> None:
        cmds = commands(_canonical_plan())
        fat_cmds = [c for c in cmds if c[0] == "newfs_msdos"]
        assert len(fat_cmds) == 1

    def test_newfs_msdos_fat32_flag(self) -> None:
        cmds = commands(_canonical_plan())
        fat_cmd = next(c for c in cmds if c[0] == "newfs_msdos")
        assert "-F" in fat_cmd
        assert "32" in fat_cmd

    def test_newfs_msdos_slice_path(self) -> None:
        # macOS slice notation: /dev/disk2s1
        cmds = commands(_canonical_plan())
        fat_cmd = next(c for c in cmds if c[0] == "newfs_msdos")
        assert "/dev/disk2s1" in fat_cmd


class TestNtfsNotFormatted:
    """NTFS is intentionally skipped on macOS (newfs_ntfs not standard)."""

    def test_no_ntfs_format_command(self) -> None:
        cmds = commands(_canonical_plan())
        ntfs_cmds = [c for c in cmds if "ntfs" in " ".join(c).lower()]
        assert ntfs_cmds == []


class TestNoSwap:
    def test_four_gpt_add_commands(self) -> None:
        disk = _make_disk(500 * _GB)
        layout = DualBootLayout(windows_size_gb=100, swap_size_gb=0)
        p = plan(disk, layout)
        cmds = commands(p)
        gpt_cmds = [c for c in cmds if c[0] == "gpt" and c[1] == "add"]
        assert len(gpt_cmds) == 4


class TestSectorAlignment:
    def test_esp_start_sector(self) -> None:
        # ESP starts at 1 MiB = 2048 sectors
        cmds = commands(_canonical_plan())
        gpt_cmds = [c for c in cmds if c[0] == "gpt" and c[1] == "add"]
        esp_cmd = gpt_cmds[0]
        b_idx = esp_cmd.index("-b")
        start_sector = int(esp_cmd[b_idx + 1])
        assert start_sector == 2048  # 1 MiB * 2048 sectors/MiB

    def test_esp_size_sectors(self) -> None:
        # ESP = 512 MiB = 512 * 2048 = 1_048_576 sectors
        cmds = commands(_canonical_plan())
        gpt_cmds = [c for c in cmds if c[0] == "gpt" and c[1] == "add"]
        esp_cmd = gpt_cmds[0]
        s_idx = esp_cmd.index("-s")
        size_sectors = int(esp_cmd[s_idx + 1])
        assert size_sectors == 512 * 2048
