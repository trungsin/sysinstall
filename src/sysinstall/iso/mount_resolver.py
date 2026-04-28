"""USB mount-point resolution and free-space pre-check for ISO operations.

These helpers are pure utility — no side effects beyond filesystem reads.
They are separated from __init__.py to keep each file under 200 LOC.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from sysinstall.disks.base import Disk
from sysinstall.iso.errors import InsufficientSpaceError, NotAVentoyUSBError

_HEADROOM_BYTES = 50 * 1024 * 1024  # 50 MiB free-space headroom


def resolve_usb_mount(disk: Disk) -> Path:
    """Return the mount point of the Ventoy first partition.

    Resolution order:
    1. ``disk.partitions[0].mountpoints[0]`` if non-empty (covers macOS
       auto-mount and pre-mounted Linux/Windows volumes).
    2. ``ventoy.mount.mount_first_partition(disk.path)`` (Linux/Windows only).

    Args:
        disk: Target disk to resolve.

    Returns:
        Path to the mount point directory.

    Raises:
        NotAVentoyUSBError: mount point found but ventoy/ventoy.json absent,
            or macOS with no auto-mounted partition.
        RuntimeError: programmatic mount failed.
    """
    mount: Path | None = None

    if disk.partitions:
        mps = disk.partitions[0].mountpoints
        if mps:
            mount = Path(mps[0])

    if mount is None:
        if sys.platform == "darwin":
            raise NotAVentoyUSBError(
                f"Disk {disk.id} has no mounted partition. "
                "Connect the Ventoy USB and ensure macOS has auto-mounted it."
            )
        # Linux / Windows: attempt programmatic mount.
        from sysinstall.ventoy.mount import mount_first_partition
        mount = mount_first_partition(disk.path)

    ventoy_json = mount / "ventoy" / "ventoy.json"
    if not ventoy_json.exists():
        raise NotAVentoyUSBError(
            f"No ventoy/ventoy.json found at {mount}. "
            f"Disk {disk.id} does not appear to be a Ventoy USB."
        )

    return mount


def check_free_space(mount: Path, iso_size: int) -> None:
    """Raise InsufficientSpaceError if the USB lacks headroom for the ISO.

    Args:
        mount: Mount point to check.
        iso_size: Size of the ISO in bytes.

    Raises:
        InsufficientSpaceError: free space < iso_size + 50 MiB.
    """
    usage = shutil.disk_usage(mount)
    required = iso_size + _HEADROOM_BYTES
    if usage.free < required:
        raise InsufficientSpaceError(required=required, available=usage.free)
