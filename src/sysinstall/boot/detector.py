"""Boot environment detector.

Identifies firmware mode (UEFI vs BIOS) and candidate partitions:
- EFI System Partitions (ESP): fat32/vfat with ESP partition type GUID
- Linux root partitions: ext4 containing /etc/os-release
- Windows partitions: NTFS containing Windows/System32

Mount probing is used to verify partition contents. All mounts are
read-only and unmounted immediately after probing.

The SYSINSTALL_FIRMWARE env var overrides firmware detection for tests:
  SYSINSTALL_FIRMWARE=uefi  -> force UEFI
  SYSINSTALL_FIRMWARE=bios  -> force BIOS
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from sysinstall.boot.types import BootEnvironment, EfiEntry, FirmwareMode
from sysinstall.disks.base import Disk, Partition

log = logging.getLogger(__name__)

# EFI System Partition type GUIDs (lowercase, with or without hyphens normalised)
_ESP_PARTTYPE_PREFIXES = ("c12a7328",)

# Filesystem types that indicate an ESP
_ESP_FS_TYPES = {"fat32", "vfat", "fat16", "fat"}

# Filesystem types that indicate a Linux root
_LINUX_FS_TYPES = {"ext4", "ext3", "ext2", "btrfs", "xfs"}

# Filesystem types that indicate Windows
_WINDOWS_FS_TYPES = {"ntfs", "ntfs-3g"}


def is_uefi() -> bool:
    """Return True if the current machine is booted in UEFI mode.

    On Linux: checks for presence of /sys/firmware/efi directory.
    On other platforms: returns False (host gate will block operations).

    Override via SYSINSTALL_FIRMWARE env var for testing:
      SYSINSTALL_FIRMWARE=uefi  -> True
      SYSINSTALL_FIRMWARE=bios  -> False
    """
    override = os.environ.get("SYSINSTALL_FIRMWARE", "").lower()
    if override == "uefi":
        return True
    if override == "bios":
        return False

    if sys.platform != "linux":
        return False

    return Path("/sys/firmware/efi").is_dir()


def _firmware_mode() -> FirmwareMode:
    return "uefi" if is_uefi() else "bios"


def _is_esp_candidate(part: Partition) -> bool:
    """Return True if partition looks like an EFI System Partition."""
    fs = (part.fs_type or "").lower()
    return fs in _ESP_FS_TYPES


def _is_linux_root_candidate(part: Partition) -> bool:
    """Return True if partition filesystem could be a Linux root."""
    fs = (part.fs_type or "").lower()
    return fs in _LINUX_FS_TYPES


def _is_windows_candidate(part: Partition) -> bool:
    """Return True if partition could be a Windows partition."""
    fs = (part.fs_type or "").lower()
    return fs in _WINDOWS_FS_TYPES


def _probe_mount_readonly(dev_path: str, check_paths: list[str]) -> bool:
    """Temporarily mount device read-only to check for specific paths.

    Returns True if ALL check_paths exist under the mount, False otherwise.
    Always unmounts even on error.

    Only runs on Linux. Returns False on other platforms.
    """
    if sys.platform != "linux":
        return False

    tmpdir = tempfile.mkdtemp(prefix="sysinstall-probe-")
    try:
        result = subprocess.run(
            ["mount", "-o", "ro", dev_path, tmpdir],
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0:
            log.debug("mount probe failed for %s: %s", dev_path, result.stderr.decode())
            return False

        try:
            mount_root = Path(tmpdir)
            return all((mount_root / p.lstrip("/")).exists() for p in check_paths)
        finally:
            subprocess.run(["umount", tmpdir], capture_output=True, timeout=30)
    except Exception as exc:  # noqa: BLE001
        log.debug("probe_mount error for %s: %s", dev_path, exc)
        return False
    finally:
        import contextlib
        with contextlib.suppress(OSError):
            Path(tmpdir).rmdir()


def _get_efi_entries_if_uefi(firmware: FirmwareMode) -> tuple[EfiEntry, ...]:
    """Return parsed EFI entries if in UEFI mode, else empty tuple."""
    if firmware != "uefi" or sys.platform != "linux":
        return ()
    try:
        from sysinstall.boot.efi import list_entries
        return tuple(list_entries())
    except Exception as exc:  # noqa: BLE001
        log.debug("Could not read efibootmgr: %s", exc)
        return ()


def find_candidates(disks: list[Disk] | None = None) -> BootEnvironment:
    """Walk all disks and classify partitions into boot candidates.

    Args:
        disks: Optional pre-loaded disk list (for testing). If None,
               calls list_disks() from sysinstall.disks.

    Returns:
        BootEnvironment with classified partition lists.
    """
    if disks is None:
        from sysinstall.disks import list_disks
        disks = list_disks()

    firmware = _firmware_mode()

    esp_candidates: list[Partition] = []
    linux_candidates: list[Partition] = []
    windows_candidates: list[Partition] = []

    for disk in disks:
        for part in disk.partitions:
            if _is_esp_candidate(part):
                esp_candidates.append(part)
                log.debug("ESP candidate: %s", part.id)
            if _is_linux_root_candidate(part):
                linux_candidates.append(part)
                log.debug("Linux root candidate: %s", part.id)
            if _is_windows_candidate(part):
                windows_candidates.append(part)
                log.debug("Windows candidate: %s", part.id)

    efi_entries = _get_efi_entries_if_uefi(firmware)

    return BootEnvironment(
        firmware=firmware,
        candidate_efi=tuple(esp_candidates),
        candidate_linux_roots=tuple(linux_candidates),
        candidate_windows=tuple(windows_candidates),
        boot_order=tuple(
            e.num for e in sorted(efi_entries, key=lambda e: e.boot_order_position)
            if e.boot_order_position >= 0
        ),
        efi_entries=efi_entries,
    )
