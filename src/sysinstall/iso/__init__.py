"""Public API for ISO management on a Ventoy USB.

Entry points:
    list_isos(disk)                         -> list[ManagedIso]
    add_iso(disk, src_path, ...)            -> ManagedIso
    remove_iso(disk, identifier)            -> ManagedIso
    verify_isos(disk, on_progress=None)     -> list[VerifyResult]

macOS: Ventoy's first partition (FAT32/exFAT) auto-mounts; mount resolution
prefers disk.partitions[0].mountpoints[0], falls back to ventoy.mount
(Linux/Windows only).
"""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sysinstall.disks.base import Disk
from sysinstall.iso.catalog import (
    ManagedIso,
    add_to_catalog,
    list_catalog,
    remove_from_catalog,
    validate_filename,
)
from sysinstall.iso.checksum import sha256_stream
from sysinstall.iso.copy import stream_copy
from sysinstall.iso.errors import InsufficientSpaceError, NotAVentoyUSBError
from sysinstall.iso.mount_resolver import check_free_space, resolve_usb_mount
from sysinstall.safety.audit import append_audit
from sysinstall.ventoy import config as ventoy_config

__all__ = [
    "ManagedIso",
    "VerifyResult",
    "NotAVentoyUSBError",
    "InsufficientSpaceError",
    "list_isos",
    "add_iso",
    "remove_iso",
    "verify_isos",
]

log = logging.getLogger(__name__)


@dataclass
class VerifyResult:
    """Outcome of verifying a single managed ISO's checksum."""

    iso: ManagedIso
    ok: bool            # True if stored sha256 matches recomputed value
    actual_sha256: str  # recomputed sha256 (empty string if file is missing)
    missing: bool       # True if the ISO file was not found on the USB


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _now_iso8601() -> str:
    return datetime.now(tz=UTC).isoformat()


def _derive_filename(src_path: Path, name: str | None) -> str:
    """Return the on-USB filename, validating it against the allowlist."""
    if name is not None:
        filename = name if name.lower().endswith(".iso") else name + ".iso"
    else:
        filename = src_path.name
    validate_filename(filename)
    return filename


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_isos(disk: Disk) -> list[ManagedIso]:
    """Return all sysinstall-managed ISOs on *disk*.

    Args:
        disk: Target Ventoy USB disk.

    Returns:
        List of :class:`ManagedIso` (may be empty).

    Raises:
        NotAVentoyUSBError: disk is not a Ventoy USB.
    """
    mount = resolve_usb_mount(disk)
    cfg = ventoy_config.read(mount)
    return list_catalog(cfg)


def add_iso(
    disk: Disk,
    src_path: Path,
    *,
    name: str | None = None,
    expected_sha: str | None = None,
    on_progress: Any | None = None,
) -> ManagedIso:
    """Copy *src_path* onto *disk* and register it in the catalog.

    Steps:
    1. Validate filename.
    2. Free-space pre-check (iso_size + 50 MiB headroom).
    3. If *expected_sha* given: verify source before copy.
    4. Stream-copy src -> USB root (atomic via .part rename).
    5. Assert post-copy sha256 == expected_sha (if given).
    6. Update ventoy.json catalog under file lock.
    7. Append audit log entry.

    Args:
        disk: Target Ventoy USB disk.
        src_path: Local path to the ISO file.
        name: Override filename on USB (default: src_path.name).
        expected_sha: Expected SHA-256 hex digest of the source ISO.
        on_progress: Callback ``(bytes_done, bytes_total)`` for copy progress.

    Returns:
        :class:`ManagedIso` as recorded in the catalog.

    Raises:
        NotAVentoyUSBError: disk is not a Ventoy USB.
        InsufficientSpaceError: USB lacks headroom.
        ValueError: checksum mismatch or invalid filename.
        FileNotFoundError: *src_path* does not exist.
    """
    src_path = Path(src_path)
    if not src_path.exists():
        raise FileNotFoundError(f"Source ISO not found: {src_path}")

    filename = _derive_filename(src_path, name)
    iso_size = src_path.stat().st_size

    mount = resolve_usb_mount(disk)
    check_free_space(mount, iso_size)

    if expected_sha is not None:
        log.info("Verifying source ISO checksum before copy...")
        source_sha = sha256_stream(src_path)
        if source_sha.lower() != expected_sha.lower():
            raise ValueError(
                f"Source ISO checksum mismatch: "
                f"expected {expected_sha!r}, got {source_sha!r}."
            )

    dst = mount / filename
    log.info("Copying %s -> %s", src_path, dst)
    _bytes_copied, post_sha = stream_copy(src_path, dst, on_progress=on_progress)

    if expected_sha is not None and post_sha.lower() != expected_sha.lower():
        with contextlib.suppress(OSError):
            dst.unlink(missing_ok=True)
        raise ValueError(
            f"Post-copy checksum mismatch: "
            f"expected {expected_sha!r}, got {post_sha!r}. "
            "The destination file has been removed."
        )

    iso = ManagedIso(
        filename=filename,
        name=name or src_path.stem,
        sha256=post_sha,
        size_bytes=iso_size,
        added_at=_now_iso8601(),
    )

    with ventoy_config.locked_rw(mount) as cfg:
        add_to_catalog(cfg, iso)

    append_audit(
        "iso.add",
        target=disk.id,
        outcome="success",
        args={"disk_id": disk.id, "filename": filename, "sha256": post_sha, "size_bytes": iso_size},
    )
    log.info("ISO %s added to %s", filename, disk.id)
    return iso


def remove_iso(disk: Disk, identifier: str) -> ManagedIso:
    """Remove *identifier* (filename or name alias) from *disk* and catalog.

    Args:
        disk: Target Ventoy USB disk.
        identifier: ISO ``filename`` or ``name`` as recorded in the catalog.

    Returns:
        The removed :class:`ManagedIso`.

    Raises:
        NotAVentoyUSBError: disk is not a Ventoy USB.
        KeyError: identifier not found in catalog.
    """
    mount = resolve_usb_mount(disk)

    with ventoy_config.locked_rw(mount) as cfg:
        removed = remove_from_catalog(cfg, identifier)

    iso_path = mount / removed.filename
    if iso_path.exists():
        iso_path.unlink()
        log.info("Deleted ISO file %s", iso_path)
    else:
        log.warning("ISO file %s not found on USB (already deleted?)", iso_path)

    append_audit(
        "iso.remove",
        target=disk.id,
        outcome="success",
        args={"disk_id": disk.id, "filename": removed.filename, "sha256": removed.sha256},
    )
    return removed


def verify_isos(disk: Disk, on_progress: Any | None = None) -> list[VerifyResult]:
    """Re-checksum all managed ISOs on *disk* and compare against stored sha256.

    Args:
        disk: Target Ventoy USB disk.
        on_progress: Callback ``(bytes_done, bytes_total)`` for each ISO.

    Returns:
        List of :class:`VerifyResult`, one per managed ISO.

    Raises:
        NotAVentoyUSBError: disk is not a Ventoy USB.
    """
    mount = resolve_usb_mount(disk)
    cfg = ventoy_config.read(mount)
    isos = list_catalog(cfg)

    results: list[VerifyResult] = []
    for iso in isos:
        iso_path = mount / iso.filename
        if not iso_path.exists():
            results.append(VerifyResult(iso=iso, ok=False, actual_sha256="", missing=True))
            continue
        actual = sha256_stream(iso_path, on_progress=on_progress)
        ok = actual.lower() == iso.sha256.lower()
        results.append(VerifyResult(iso=iso, ok=ok, actual_sha256=actual, missing=False))

    return results
