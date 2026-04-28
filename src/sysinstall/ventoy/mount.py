"""Cross-platform mount/unmount helpers for Ventoy's first partition.

macOS: irrelevant (we hard-fail before reaching mount calls).
Linux: uses udisksctl when available, falls back to mount(8).
Windows: uses mountvol to assign/remove drive letters.

All subprocess calls use list args — no shell=True.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

_SUBPROCESS_TIMEOUT = 30


def _run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    log.debug("Running: %s", " ".join(cmd))
    return subprocess.run(  # noqa: S603
        cmd,
        capture_output=True,
        text=True,
        timeout=_SUBPROCESS_TIMEOUT,
        check=check,
    )


# ---------------------------------------------------------------------------
# Linux helpers
# ---------------------------------------------------------------------------

def _linux_mount(partition: str) -> Path:
    """Mount *partition* (e.g. /dev/sdb1) and return the mount point."""
    # Try udisksctl first (no root needed on most desktop distros).
    try:
        result = _run(["udisksctl", "mount", "-b", partition])
        # udisksctl prints: "Mounted /dev/sdb1 at /run/media/user/VENTOY"
        for token in result.stdout.split():
            if token.startswith("/") and token != partition:
                log.info("Mounted %s at %s (udisksctl)", partition, token)
                return Path(token.rstrip("."))
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        log.debug("udisksctl unavailable or failed; falling back to mount(8)")

    # Fallback: create a tempdir and use mount(8) (requires root).
    mount_point = Path(tempfile.mkdtemp(prefix="sysinstall_ventoy_"))
    _run(["mount", partition, str(mount_point)])
    log.info("Mounted %s at %s (mount)", partition, mount_point)
    return mount_point


def _linux_unmount(mount_point: Path) -> None:
    """Unmount *mount_point* using udisksctl or umount(8)."""
    try:
        _run(["udisksctl", "unmount", "-b", str(mount_point)])
        return
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass
    _run(["umount", str(mount_point)], check=False)


def _linux_unmount_partition(partition: str) -> None:
    """Unmount a partition by device path before Ventoy install."""
    try:
        _run(["udisksctl", "unmount", "-b", partition], check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        _run(["umount", partition], check=False)


# ---------------------------------------------------------------------------
# Windows helpers
# ---------------------------------------------------------------------------

def _windows_mount(partition_path: str) -> Path:
    """Assign a drive letter to *partition_path* and return it as a Path.

    *partition_path* is a volume GUID path like
    \\\\?\\Volume{guid}\\ as returned by mountvol.
    """
    # Find an available drive letter by trying D: through Z:.
    for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
        drive = f"{letter}:\\"
        result = _run(["mountvol", drive, partition_path], check=False)
        if result.returncode == 0:
            log.info("Mounted %s at %s", partition_path, drive)
            return Path(drive)
    raise RuntimeError("No available drive letter to mount Ventoy partition.")


def _windows_unmount(mount_point: Path) -> None:
    """Remove the drive letter assigned by _windows_mount."""
    _run(["mountvol", str(mount_point), "/D"], check=False)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def mount_first_partition(device_path: str) -> Path:
    """Mount Ventoy's first partition and return its mount point.

    Args:
        device_path: Block device path (Linux: /dev/sdb, Windows: \\\\.\\PhysicalDrive1).

    Returns:
        Path to the mount point directory.

    Raises:
        RuntimeError: mount failed and no fallback succeeded.
        NotImplementedError: called on macOS (should never happen — caller hard-fails first).
    """
    if sys.platform == "darwin":
        raise NotImplementedError("macOS USB creation is not supported.")

    if sys.platform == "win32":
        # Windows auto-mount requires a volume GUID path; caller must pass it directly.
        # mountvol can list available volumes but mapping device->partition GUID
        # requires WMI or PowerShell — deferred to integration layer.
        raise NotImplementedError(
            "Windows auto-mount requires volume GUID — pass partition_path directly."
        )

    # Linux: first partition is device_path + "1" (e.g. /dev/sdb -> /dev/sdb1).
    partition = _first_partition_path(device_path)
    return _linux_mount(partition)


def unmount_partition(mount_point_or_device: str) -> None:
    """Unmount a previously mounted partition.

    Args:
        mount_point_or_device: Either a mount point path or a device path.
    """
    if sys.platform == "darwin":
        raise NotImplementedError("macOS USB creation is not supported.")

    if sys.platform == "win32":
        _windows_unmount(Path(mount_point_or_device))
        return

    _linux_unmount(Path(mount_point_or_device))


def unmount_all_partitions(device_path: str) -> None:
    """Unmount all partitions of *device_path* before Ventoy install.

    Best-effort — errors are logged but not raised.

    Args:
        device_path: Base device path, e.g. /dev/sdb.
    """
    if sys.platform == "darwin":
        raise NotImplementedError("macOS USB creation is not supported.")

    if sys.platform == "win32":
        log.warning("unmount_all_partitions: Windows auto-unmount not implemented.")
        return

    # Try up to 8 partitions.
    for i in range(1, 9):
        partition = f"{device_path}{i}"
        try:
            _linux_unmount_partition(partition)
        except Exception as exc:  # noqa: BLE001
            log.debug("Could not unmount %s: %s", partition, exc)


def _first_partition_path(device_path: str) -> str:
    """Return the first partition path for a block device.

    E.g. /dev/sdb -> /dev/sdb1, /dev/nvme0n1 -> /dev/nvme0n1p1
    """
    import re
    if re.search(r"nvme\d+n\d+$", device_path):
        return device_path + "p1"
    return device_path + "1"
