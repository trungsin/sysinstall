"""Linux disk backend — uses lsblk(8) via subprocess + JSON parsing.

Architecture:
  - parse_lsblk(json_bytes)  -> list[Disk]   pure function; unit-testable
  - _run_lsblk()             -> bytes         thin subprocess wrapper
  - LinuxBackend             implements DiskBackend Protocol

System disk detection: any partition with mountpoint in {/, /boot, /boot/efi}.
"""

from __future__ import annotations

import json
import re
import subprocess
from typing import Any, cast

from sysinstall.disks.base import BackendUnavailable, BusType, Disk, Partition
from sysinstall.disks.identifiers import make_stable_id

_SUBPROCESS_TIMEOUT = 15

_SYSTEM_MOUNTPOINTS = frozenset(["/", "/boot", "/boot/efi"])

# Map lsblk TRAN field to normalised bus type.
_BUS_MAP: dict[str, str] = {
    "usb": "usb",
    "sata": "sata",
    "nvme": "nvme",
    "scsi": "scsi",
    "sas": "scsi",
    "ata": "sata",
    "ide": "sata",
}


def _normalise_bus(tran: str | None) -> BusType:
    if not tran:
        return "unknown"
    return cast(BusType, _BUS_MAP.get(tran.lower().strip(), "unknown"))


# ---------------------------------------------------------------------------
# Pure parsers — no subprocess; fully unit-testable.
# ---------------------------------------------------------------------------

def parse_lsblk(json_bytes: bytes) -> list[Disk]:
    """Parse ``lsblk -J -O -p -b`` JSON output into a list of :class:`Disk`.

    Only top-level block devices of type "disk" are returned.
    """
    data: dict[str, Any] = json.loads(json_bytes)
    devices: list[dict[str, Any]] = data.get("blockdevices", [])

    disks: list[Disk] = []
    for order, dev in enumerate(devices):
        if dev.get("type") != "disk":
            continue
        disk = _build_disk(dev, order)
        disks.append(disk)
    return disks


def _build_disk(dev: dict[str, Any], order: int) -> Disk:
    path: str = dev.get("path") or dev.get("name") or ""
    size_bytes: int = int(dev.get("size") or 0)
    model: str = (dev.get("model") or "").strip() or "Unknown"
    serial: str | None = (dev.get("serial") or "").strip() or None
    tran: str | None = dev.get("tran")
    bus = _normalise_bus(tran)

    rm_raw = dev.get("rm") or dev.get("removable")
    is_removable = bool(rm_raw) if not isinstance(rm_raw, bool) else rm_raw
    if isinstance(rm_raw, str):
        is_removable = rm_raw.strip() not in ("0", "", "false", "False")

    children: list[dict[str, Any]] = dev.get("children") or []
    partitions = _build_partitions(children)
    is_system = _detect_system(children)

    disk_id = make_stable_id(bus, serial, model, size_bytes, order)

    return Disk(
        id=disk_id,
        path=path,
        size_bytes=size_bytes,
        model=model,
        serial=serial,
        bus=bus,
        is_removable=is_removable,
        is_system=is_system,
        partitions=tuple(partitions),
    )


def _detect_system(children: list[dict[str, Any]]) -> bool:
    """Return True if any child partition has a system mountpoint."""
    for child in children:
        mps = _extract_mountpoints(child)
        if any(mp in _SYSTEM_MOUNTPOINTS for mp in mps):
            return True
        # Recurse into LVM/RAID children.
        sub = child.get("children") or []
        if _detect_system(sub):
            return True
    return False


def _extract_mountpoints(dev: dict[str, Any]) -> list[str]:
    """Extract mountpoints from a device dict (handles both str and list forms)."""
    raw = dev.get("mountpoints") or dev.get("mountpoint")
    if raw is None:
        return []
    if isinstance(raw, list):
        return [m for m in raw if m]
    if isinstance(raw, str) and raw:
        return [raw]
    return []


def _build_partitions(children: list[dict[str, Any]]) -> list[Partition]:
    parts: list[Partition] = []
    for child in children:
        dev_type = child.get("type", "")
        if dev_type not in ("part", "lvm", "md", "crypt", ""):
            continue
        mps = tuple(_extract_mountpoints(child))
        parts.append(Partition(
            id=child.get("path") or child.get("name") or "",
            fs_type=child.get("fstype") or None,
            size_bytes=int(child.get("size") or 0),
            mountpoints=mps,
            label=child.get("label") or None,
        ))
    return parts


# ---------------------------------------------------------------------------
# Subprocess wrapper
# ---------------------------------------------------------------------------

def _run_lsblk() -> bytes:
    """Invoke ``lsblk -J -O -p -b`` and return stdout bytes.

    Raises:
        BackendUnavailable: if lsblk is missing, times out, or exits non-zero.
    """
    cmd = ["lsblk", "-J", "-O", "-p", "-b"]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=_SUBPROCESS_TIMEOUT,
        )
    except FileNotFoundError as exc:
        raise BackendUnavailable("lsblk not found — not running on Linux?") from exc
    except subprocess.TimeoutExpired as exc:
        raise BackendUnavailable(f"lsblk timed out after {_SUBPROCESS_TIMEOUT}s") from exc
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace").strip()
        raise BackendUnavailable(f"lsblk exited {result.returncode}: {stderr}")
    return result.stdout


# ---------------------------------------------------------------------------
# Backend implementation
# ---------------------------------------------------------------------------

class LinuxBackend:
    """DiskBackend implementation for Linux using lsblk."""

    def list_disks(self) -> list[Disk]:
        return parse_lsblk(_run_lsblk())

    def get_disk(self, disk_id: str) -> Disk:
        if not re.match(r"^[a-zA-Z0-9:.\-]+$", disk_id):
            raise KeyError(f"Invalid disk ID format: {disk_id!r}")
        for disk in self.list_disks():
            if disk.id == disk_id:
                return disk
        raise KeyError(f"Disk not found: {disk_id!r}")
