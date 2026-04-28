"""Pre-flight checks before partitioning: encryption detection and unmounting.

SHIM MODULE — canonical implementations moved to sysinstall.safety.gates (Phase 07).
This module re-exports from there for backwards compatibility. Thin wrapper
functions are kept so that existing tests can patch this module's namespace.

All new callers should import from sysinstall.safety.gates directly.

TODO(v2): remove this shim once all callers are migrated to safety.gates.
"""

from __future__ import annotations

import subprocess
import sys
from enum import Enum

from sysinstall.disks.base import Disk

# Re-export unmount_all directly (no wrapper needed — tests patch sys.platform).
from sysinstall.safety.gates import unmount_all  # noqa: F401 — re-exported

__all__ = [
    "EncryptionStatus",
    "check_encryption",
    "unmount_all",
    "_check_linux",
    "_check_macos",
    "_check_windows",
    "_tool_available",
]

_CMD_TIMEOUT = 30


class EncryptionStatus(Enum):
    """Detected encryption state of a disk.

    Maps the string return value of safety.gates.detect_encryption() to the
    original enum for backwards compatibility.
    """

    none = "none"
    partial = "partial"
    full = "full"
    unknown = "unknown"


# ---------------------------------------------------------------------------
# Thin wrappers — kept so tests can patch sysinstall.partition.preflight.*
# These delegate to gates helpers but call module-level _tool_available so
# existing tests that patch this namespace continue to work.
# ---------------------------------------------------------------------------


def _tool_available(name: str) -> bool:
    """Return True if *name* resolves to an executable on PATH."""
    try:
        subprocess.run(  # noqa: S603
            ["which", name],
            capture_output=True,
            timeout=5,
        )
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _check_linux(disk: Disk) -> EncryptionStatus:
    """Check each partition for LUKS magic via cryptsetup isLuks."""
    if not disk.partitions:
        return EncryptionStatus.none

    if not _tool_available("cryptsetup"):
        return EncryptionStatus.unknown

    encrypted_count = 0
    for part in disk.partitions:
        try:
            ret = subprocess.run(  # noqa: S603
                ["cryptsetup", "isLuks", part.id],
                capture_output=True,
                timeout=_CMD_TIMEOUT,
            )
            if ret.returncode == 0:
                encrypted_count += 1
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return EncryptionStatus.unknown

    if encrypted_count == 0:
        return EncryptionStatus.none
    if encrypted_count == len(disk.partitions):
        return EncryptionStatus.full
    return EncryptionStatus.partial


def _check_macos(disk: Disk) -> EncryptionStatus:
    """Check FileVault via fdesetup; also scan for APFS encrypted containers."""
    try:
        result = subprocess.run(  # noqa: S603
            ["fdesetup", "status"],
            capture_output=True,
            text=True,
            timeout=_CMD_TIMEOUT,
        )
        output = result.stdout.lower()
        if "on" in output:
            return EncryptionStatus.full
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return EncryptionStatus.unknown

    try:
        result = subprocess.run(  # noqa: S603
            ["diskutil", "apfs", "list", "-plist"],
            capture_output=True,
            text=True,
            timeout=_CMD_TIMEOUT,
        )
        if disk.path in result.stdout and "encrypted" in result.stdout.lower():
            return EncryptionStatus.partial
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return EncryptionStatus.none


def _check_windows(disk: Disk) -> EncryptionStatus:  # noqa: ARG001
    """Check BitLocker via Get-BitLockerVolume."""
    try:
        result = subprocess.run(  # noqa: S603
            [
                "powershell.exe",
                "-NonInteractive",
                "-Command",
                "Get-BitLockerVolume | Select-Object -ExpandProperty ProtectionStatus",
            ],
            capture_output=True,
            text=True,
            timeout=_CMD_TIMEOUT,
        )
        lines = [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]
        if not lines:
            return EncryptionStatus.none
        on_count = sum(1 for ln in lines if ln.lower() == "on")
        if on_count == 0:
            return EncryptionStatus.none
        if on_count == len(lines):
            return EncryptionStatus.full
        return EncryptionStatus.partial
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return EncryptionStatus.unknown


# ---------------------------------------------------------------------------
# Public API (backwards-compatible wrappers)
# ---------------------------------------------------------------------------


def check_encryption(disk: Disk) -> EncryptionStatus:
    """Probe *disk* for full-disk or partition-level encryption.

    Delegates to platform-specific helpers in this module (which mirror
    sysinstall.safety.gates canonical implementations). The gates module is
    the single source of truth for new callers.

    Args:
        disk: Target disk to inspect.

    Returns:
        :class:`EncryptionStatus` enum value.
    """
    # TODO(v2): migrate callers to safety.gates.detect_encryption() directly.
    if sys.platform == "linux":
        return _check_linux(disk)
    if sys.platform == "darwin":
        return _check_macos(disk)
    if sys.platform == "win32":
        return _check_windows(disk)
    return EncryptionStatus.unknown
