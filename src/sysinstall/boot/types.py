"""Frozen dataclasses for the boot module's domain types.

All types are immutable (frozen=True) to prevent accidental mutation
after construction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from sysinstall.disks.base import Partition

FirmwareMode = Literal["uefi", "bios"]


@dataclass(frozen=True)
class EfiEntry:
    """A single entry from efibootmgr -v output.

    num: 4-digit hex string, e.g. "0001"
    label: human-readable name, e.g. "ubuntu"
    path: EFI device path string (may be empty for inactive entries)
    active: whether the entry has the * (active) flag
    boot_order_position: index in BootOrder list (-1 = not in order)
    """

    num: str
    label: str
    path: str
    active: bool
    boot_order_position: int = -1


@dataclass(frozen=True)
class BootEnvironment:
    """Result of boot environment detection.

    firmware: detected firmware mode ("uefi" or "bios")
    candidate_efi: partitions that look like EFI System Partitions
    candidate_linux_roots: partitions with /etc/os-release
    candidate_windows: NTFS partitions containing Windows/System32
    boot_order: raw BootOrder from efibootmgr (uefi only, else empty)
    efi_entries: parsed EFI entries (uefi only, else empty)
    """

    firmware: FirmwareMode
    candidate_efi: tuple[Partition, ...]
    candidate_linux_roots: tuple[Partition, ...]
    candidate_windows: tuple[Partition, ...]
    boot_order: tuple[str, ...] = field(default_factory=tuple)
    efi_entries: tuple[EfiEntry, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class RepairPlan:
    """Everything needed to execute a boot repair.

    firmware: firmware mode for this machine
    efi_partition: the EFI System Partition to use (uefi mode only)
    root_partition: the Ubuntu root partition to chroot into
    enable_os_prober: whether to set GRUB_DISABLE_OS_PROBER=false
    set_boot_order_first: whether to move Ubuntu to top of EFI boot order
    """

    firmware: FirmwareMode
    efi_partition: Partition | None
    root_partition: Partition
    enable_os_prober: bool
    set_boot_order_first: bool


class UnsupportedHostError(Exception):
    """Raised when the current host OS cannot run boot repair operations."""
