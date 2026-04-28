"""Public API for disk enumeration — platform-agnostic entry point.

Usage:
    from sysinstall.disks import list_disks, get_disk

Backend selection is automatic based on sys.platform:
    darwin  -> MacOSBackend
    win32   -> WindowsBackend
    else    -> LinuxBackend
"""

from __future__ import annotations

import sys

from sysinstall.disks.base import BackendUnavailable, Disk, DiskBackend, Partition

__all__ = [
    "list_disks",
    "get_disk",
    "Disk",
    "Partition",
    "BackendUnavailable",
]


def _backend() -> DiskBackend:
    """Return the appropriate platform backend instance."""
    if sys.platform == "darwin":
        from sysinstall.disks.macos import MacOSBackend
        return MacOSBackend()
    if sys.platform == "win32":
        from sysinstall.disks.windows import WindowsBackend
        return WindowsBackend()
    from sysinstall.disks.linux import LinuxBackend
    return LinuxBackend()


def list_disks() -> list[Disk]:
    """Enumerate all physical whole disks on the current host.

    Returns:
        List of :class:`Disk` instances. Empty list if no disks found.

    Raises:
        BackendUnavailable: if the platform tool is missing or fails.
    """
    return _backend().list_disks()


def get_disk(disk_id: str) -> Disk:
    """Re-resolve a disk by its stable ID.

    Args:
        disk_id: Stable ID string as returned by :func:`list_disks`.

    Returns:
        The matching :class:`Disk` instance.

    Raises:
        KeyError: if no disk with the given ID is found.
        BackendUnavailable: if the platform tool is missing or fails.
    """
    return _backend().get_disk(disk_id)
