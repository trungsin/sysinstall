"""Base dataclasses and Protocol for disk backends."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

BusType = Literal["usb", "sata", "nvme", "scsi", "unknown"]

# Regex pattern for validating disk IDs before passing back to backends.
DISK_ID_PATTERN = r"^[a-zA-Z0-9:.\-]+$"


@dataclass(frozen=True)
class Partition:
    """Represents a single partition on a physical disk."""

    id: str
    fs_type: str | None
    size_bytes: int
    mountpoints: tuple[str, ...]
    label: str | None


@dataclass(frozen=True)
class Disk:
    """Represents a physical whole disk (not a synthesized volume)."""

    id: str  # stable: e.g. "nvme:ABC123:500277792768" or "unstable:model:size:0"
    path: str  # current device path: /dev/disk0, \\.\PhysicalDrive0, etc.
    size_bytes: int
    model: str
    serial: str | None
    bus: BusType
    is_removable: bool
    is_system: bool
    partitions: tuple[Partition, ...]


class DiskBackend(Protocol):
    """Protocol that all platform backends must implement."""

    def list_disks(self) -> list[Disk]:
        """Enumerate all physical disks on the host."""
        ...

    def get_disk(self, disk_id: str) -> Disk:
        """Re-resolve a disk by its stable ID. Raises KeyError if not found."""
        ...


class BackendUnavailable(Exception):
    """Raised when the platform tool (diskutil, lsblk, PowerShell) is unavailable
    or returns a non-zero exit code."""
