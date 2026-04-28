"""Assert exact sgdisk + mkfs arg lists for the Linux runner command builder."""

from __future__ import annotations

from sysinstall.disks.base import Disk
from sysinstall.partition.layout import DualBootLayout
from sysinstall.partition.planner import plan
from sysinstall.partition.runner_linux import _part_path, commands

_GB = 1024 * 1024 * 1024


def _make_disk(size_bytes: int, path: str = "/dev/sdb") -> Disk:
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


def _canonical_plan(path: str = "/dev/sdb"):
    disk = _make_disk(500 * _GB, path)
    layout = DualBootLayout(windows_size_gb=100, swap_size_gb=4)
    return plan(disk, layout)


class TestSgdiskArgs:
    def test_first_command_is_sgdisk(self) -> None:
        cmds = commands(_canonical_plan())
        assert cmds[0][0] == "sgdisk"

    def test_sgdisk_zap_all_flag(self) -> None:
        cmds = commands(_canonical_plan())
        assert "--zap-all" in cmds[0]

    def test_sgdisk_last_arg_is_disk_path(self) -> None:
        cmds = commands(_canonical_plan())
        assert cmds[0][-1] == "/dev/sdb"

    def test_sgdisk_has_five_new_partition_flags(self) -> None:
        cmds = commands(_canonical_plan())
        sgdisk_args = cmds[0]
        new_flags = [a for a in sgdisk_args if a.startswith("--new=")]
        assert len(new_flags) == 5

    def test_sgdisk_esp_new_arg(self) -> None:
        cmds = commands(_canonical_plan())
        sgdisk_args = cmds[0]
        # ESP is partition 1, starts at sector 2048 (1 MiB * 2048 sectors/MiB)
        assert "--new=1:2048:1050623" in sgdisk_args  # start=2048, end=1*2048 + 512*2048 - 1

    def test_sgdisk_esp_typecode(self) -> None:
        cmds = commands(_canonical_plan())
        sgdisk_args = cmds[0]
        assert "--typecode=1:C12A7328-F81F-11D2-BA4B-00A0C93EC93B" in sgdisk_args

    def test_sgdisk_esp_name(self) -> None:
        cmds = commands(_canonical_plan())
        sgdisk_args = cmds[0]
        assert "--change-name=1:EFI" in sgdisk_args

    def test_sgdisk_windows_typecode(self) -> None:
        cmds = commands(_canonical_plan())
        sgdisk_args = cmds[0]
        assert "--typecode=3:EBD0A0A2-B9E5-4433-87C0-68B6B72699C7" in sgdisk_args

    def test_sgdisk_linux_fs_typecode(self) -> None:
        cmds = commands(_canonical_plan())
        sgdisk_args = cmds[0]
        assert "--typecode=4:0FC63DAF-8483-4772-8E79-3D69D8477DE4" in sgdisk_args

    def test_sgdisk_swap_typecode(self) -> None:
        cmds = commands(_canonical_plan())
        sgdisk_args = cmds[0]
        assert "--typecode=5:0657FD6D-A4AB-43C4-84E5-0933C84B4F4F" in sgdisk_args


class TestMkfsCommands:
    def setup_method(self) -> None:
        self.cmds = commands(_canonical_plan())
        # cmds[0] = sgdisk, then mkfs commands, then partprobe + udevadm
        self.mkfs_cmds = [c for c in self.cmds if c[0].startswith("mkfs") or c[0] == "mkswap"]

    def test_mkfs_fat_for_esp(self) -> None:
        fat_cmd = next((c for c in self.mkfs_cmds if c[0] == "mkfs.fat"), None)
        assert fat_cmd is not None
        assert "-F" in fat_cmd
        assert "32" in fat_cmd
        assert "/dev/sdb1" in fat_cmd

    def test_mkfs_ntfs_for_windows(self) -> None:
        ntfs_cmd = next((c for c in self.mkfs_cmds if c[0] == "mkfs.ntfs"), None)
        assert ntfs_cmd is not None
        assert "-Q" in ntfs_cmd
        assert "/dev/sdb3" in ntfs_cmd

    def test_mkfs_ext4_for_ubuntu(self) -> None:
        ext4_cmd = next((c for c in self.mkfs_cmds if c[0] == "mkfs.ext4"), None)
        assert ext4_cmd is not None
        assert "/dev/sdb4" in ext4_cmd

    def test_mkswap_for_swap(self) -> None:
        swap_cmd = next((c for c in self.mkfs_cmds if c[0] == "mkswap"), None)
        assert swap_cmd is not None
        assert "/dev/sdb5" in swap_cmd

    def test_no_mkfs_for_msr(self) -> None:
        # MSR partition (unallocated) must not have a mkfs command
        msr_cmds = [c for c in self.mkfs_cmds if "/dev/sdb2" in c]
        assert msr_cmds == []


class TestPostlude:
    def test_partprobe_present(self) -> None:
        cmds = commands(_canonical_plan())
        assert ["partprobe", "/dev/sdb"] in cmds

    def test_udevadm_settle_present(self) -> None:
        cmds = commands(_canonical_plan())
        assert ["udevadm", "settle"] in cmds

    def test_postlude_at_end(self) -> None:
        cmds = commands(_canonical_plan())
        assert cmds[-2] == ["partprobe", "/dev/sdb"]
        assert cmds[-1] == ["udevadm", "settle"]


class TestNvmePartPath:
    def test_nvme_uses_p_separator(self) -> None:
        assert _part_path("/dev/nvme0n1", 1) == "/dev/nvme0n1p1"

    def test_sata_uses_direct_suffix(self) -> None:
        assert _part_path("/dev/sdb", 3) == "/dev/sdb3"


class TestNoSwapPlan:
    def test_four_partitions_no_swap_cmd(self) -> None:
        disk = _make_disk(500 * _GB)
        layout = DualBootLayout(windows_size_gb=100, swap_size_gb=0)
        p = plan(disk, layout)
        cmds = commands(p)
        swap_cmds = [c for c in cmds if c[0] == "mkswap"]
        assert swap_cmds == []
        new_flags = [a for a in cmds[0] if a.startswith("--new=")]
        assert len(new_flags) == 4
