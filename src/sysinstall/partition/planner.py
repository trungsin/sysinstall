"""Pure partition planner — disk + layout -> PartitionPlan.

No subprocess calls here; fully testable as unit tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sysinstall.disks.base import Disk
from sysinstall.partition.layout import (
    GUID_ESP,
    GUID_LINUX_FS,
    GUID_LINUX_SWAP,
    GUID_MSR,
    GUID_WINDOWS,
    DualBootLayout,
    LayoutTooLargeError,
)

FsType = Literal["fat32", "ntfs", "ext4", "swap", "unallocated"]

_ESP_MB = 512
_MSR_MB = 16
_MB = 1024 * 1024


@dataclass(frozen=True)
class PlannedPartition:
    """A single partition slot in the planned layout.

    Attributes:
        index: 1-based partition number.
        label: Human-readable label / filesystem label.
        size_mb: Partition size in MiB; None means "use all remaining space".
        fs: Filesystem type to create (or 'unallocated' if host cannot format).
        type_guid: GPT partition type GUID.
        mountpoint_hint: Suggested Linux mountpoint, if applicable.
    """

    index: int
    label: str
    size_mb: int | None
    fs: FsType
    type_guid: str
    mountpoint_hint: str | None


@dataclass(frozen=True)
class PartitionPlan:
    """Fully resolved partition plan for a target disk.

    Attributes:
        disk: Target disk.
        partitions: Ordered tuple of planned partitions.
        total_required_mb: Sum of all fixed-size partitions (excludes "remaining").
    """

    disk: Disk
    partitions: tuple[PlannedPartition, ...]
    total_required_mb: int


def plan(disk: Disk, layout: DualBootLayout) -> PartitionPlan:
    """Compute the dual-boot partition plan for *disk* given *layout*.

    All arithmetic is done in MiB. The Ubuntu root partition gets whatever
    space remains after ESP + MSR + Windows + swap (if any).

    Args:
        disk: Target disk (used for capacity check only here; safety guards
              must be applied by the caller before reaching this function).
        layout: Validated :class:`DualBootLayout` instance.

    Returns:
        :class:`PartitionPlan` with a frozen tuple of :class:`PlannedPartition`.

    Raises:
        LayoutTooLargeError: The plan does not fit on the disk.
    """
    disk_mb = disk.size_bytes // _MB

    # Fixed-size partitions (MiB)
    windows_mb = layout.windows_size_gb * 1024
    swap_mb = layout.swap_size_gb * 1024  # 0 when no-swap

    fixed_mb = _ESP_MB + _MSR_MB + windows_mb + swap_mb
    ubuntu_mb = disk_mb - fixed_mb

    if ubuntu_mb < 1:
        raise LayoutTooLargeError(
            f"Not enough space for Ubuntu root: disk={disk_mb} MiB, "
            f"fixed={fixed_mb} MiB, remaining={ubuntu_mb} MiB."
        )

    # Minimum sensible Ubuntu root: 10 GiB
    if ubuntu_mb < 10 * 1024:
        raise LayoutTooLargeError(
            f"Ubuntu root would only be {ubuntu_mb} MiB (< 10 GiB). "
            "Increase disk size or reduce Windows/swap allocation."
        )

    partitions: list[PlannedPartition] = [
        PlannedPartition(
            index=1,
            label="EFI",
            size_mb=_ESP_MB,
            fs="fat32",
            type_guid=GUID_ESP,
            mountpoint_hint="/boot/efi",
        ),
        PlannedPartition(
            index=2,
            label="MSR",
            size_mb=_MSR_MB,
            fs="unallocated",
            type_guid=GUID_MSR,
            mountpoint_hint=None,
        ),
        PlannedPartition(
            index=3,
            label="Windows",
            size_mb=windows_mb,
            fs="ntfs",
            type_guid=GUID_WINDOWS,
            mountpoint_hint=None,
        ),
        PlannedPartition(
            index=4,
            label="Ubuntu",
            size_mb=ubuntu_mb,
            fs="ext4",
            type_guid=GUID_LINUX_FS,
            mountpoint_hint="/",
        ),
    ]

    if layout.swap_size_gb > 0:
        partitions.append(
            PlannedPartition(
                index=5,
                label="swap",
                size_mb=swap_mb,
                fs="swap",
                type_guid=GUID_LINUX_SWAP,
                mountpoint_hint="[SWAP]",
            )
        )

    total_required_mb = fixed_mb

    return PartitionPlan(
        disk=disk,
        partitions=tuple(partitions),
        total_required_mb=total_required_mb,
    )
