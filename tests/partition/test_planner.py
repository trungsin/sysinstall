"""Table-driven tests for the partition planner."""

from __future__ import annotations

import pytest

from sysinstall.disks.base import Disk
from sysinstall.partition.layout import DualBootLayout, LayoutTooLargeError
from sysinstall.partition.planner import PartitionPlan, plan

_MB = 1024 * 1024
_GB = 1024 * _MB


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


class TestPlannerDefault500GB:
    """500 GB disk, windows=100 GB, swap=4 GB (defaults)."""

    def setup_method(self) -> None:
        disk = _make_disk(500 * _GB)
        layout = DualBootLayout(windows_size_gb=100, swap_size_gb=4)
        self.result: PartitionPlan = plan(disk, layout)

    def test_partition_count_five(self) -> None:
        assert len(self.result.partitions) == 5

    def test_esp_partition(self) -> None:
        esp = self.result.partitions[0]
        assert esp.index == 1
        assert esp.label == "EFI"
        assert esp.size_mb == 512
        assert esp.fs == "fat32"
        assert esp.mountpoint_hint == "/boot/efi"

    def test_msr_partition(self) -> None:
        msr = self.result.partitions[1]
        assert msr.index == 2
        assert msr.label == "MSR"
        assert msr.size_mb == 16
        assert msr.fs == "unallocated"

    def test_windows_partition(self) -> None:
        win = self.result.partitions[2]
        assert win.index == 3
        assert win.label == "Windows"
        assert win.size_mb == 100 * 1024
        assert win.fs == "ntfs"

    def test_ubuntu_partition_gets_remaining(self) -> None:
        ubuntu = self.result.partitions[3]
        assert ubuntu.index == 4
        assert ubuntu.label == "Ubuntu"
        assert ubuntu.fs == "ext4"
        assert ubuntu.mountpoint_hint == "/"
        # 500*1024 - 512 - 16 - 100*1024 - 4*1024 = 395384 MiB
        expected_mb = 500 * 1024 - 512 - 16 - 100 * 1024 - 4 * 1024
        assert ubuntu.size_mb == expected_mb

    def test_swap_partition(self) -> None:
        swap = self.result.partitions[4]
        assert swap.index == 5
        assert swap.label == "swap"
        assert swap.size_mb == 4 * 1024
        assert swap.fs == "swap"
        assert swap.mountpoint_hint == "[SWAP]"

    def test_total_required_mb(self) -> None:
        # fixed: ESP + MSR + windows + swap
        expected = 512 + 16 + 100 * 1024 + 4 * 1024
        assert self.result.total_required_mb == expected


class TestPlanner1TBWith8GBSwap:
    """1 TB disk, windows=200 GB, swap=8 GB."""

    def test_plan(self) -> None:
        disk = _make_disk(1024 * _GB)
        layout = DualBootLayout(windows_size_gb=200, swap_size_gb=8)
        result = plan(disk, layout)
        assert len(result.partitions) == 5
        ubuntu = result.partitions[3]
        expected_ubuntu_mb = 1024 * 1024 - 512 - 16 - 200 * 1024 - 8 * 1024
        assert ubuntu.size_mb == expected_ubuntu_mb


class TestPlannerNoSwap:
    """No-swap option reduces partition count to 4."""

    def test_four_partitions(self) -> None:
        disk = _make_disk(500 * _GB)
        layout = DualBootLayout(windows_size_gb=100, swap_size_gb=0)
        result = plan(disk, layout)
        assert len(result.partitions) == 4
        labels = [p.label for p in result.partitions]
        assert "swap" not in labels

    def test_ubuntu_gets_all_remaining(self) -> None:
        disk = _make_disk(500 * _GB)
        layout = DualBootLayout(windows_size_gb=100, swap_size_gb=0)
        result = plan(disk, layout)
        ubuntu = result.partitions[3]
        expected_mb = 500 * 1024 - 512 - 16 - 100 * 1024
        assert ubuntu.size_mb == expected_mb


class TestPlannerTinyDisk:
    """Tiny disk raises LayoutTooLargeError."""

    def test_raises_on_20gb_disk(self) -> None:
        disk = _make_disk(20 * _GB)
        layout = DualBootLayout(windows_size_gb=30, swap_size_gb=0)
        with pytest.raises(LayoutTooLargeError):
            plan(disk, layout)

    def test_raises_when_ubuntu_would_be_tiny(self) -> None:
        # 40 GB disk: ESP+MSR+Win(30)+swap(4) = 34.5 GB, leaves ~5.5 GB < 10 GiB min
        disk = _make_disk(40 * _GB)
        layout = DualBootLayout(windows_size_gb=30, swap_size_gb=4)
        with pytest.raises(LayoutTooLargeError):
            plan(disk, layout)


class TestPlannerPartitionsAreFrozen:
    """PartitionPlan.partitions is a frozen tuple."""

    def test_tuple_type(self) -> None:
        disk = _make_disk(500 * _GB)
        layout = DualBootLayout(windows_size_gb=100, swap_size_gb=4)
        result = plan(disk, layout)
        assert isinstance(result.partitions, tuple)

    def test_planned_partition_is_frozen(self) -> None:
        disk = _make_disk(500 * _GB)
        layout = DualBootLayout(windows_size_gb=100, swap_size_gb=4)
        result = plan(disk, layout)
        with pytest.raises(Exception):  # frozen dataclass raises FrozenInstanceError
            result.partitions[0].label = "hack"  # type: ignore[misc]
