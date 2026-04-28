"""Windows disk backend — uses PowerShell Get-Disk/Get-Partition/Get-Volume.

Architecture:
  - parse_powershell_disks(disk_json, partition_json, volume_json) -> list[Disk]
    pure function; unit-testable via fixtures.
  - _run_powershell(script)  -> bytes   thin subprocess wrapper
  - WindowsBackend           implements DiskBackend Protocol

System disk detection: IsBoot == True OR IsSystem == True on a Get-Disk entry.
"""

from __future__ import annotations

import json
import re
import subprocess
from typing import Any, cast

from sysinstall.disks.base import BackendUnavailable, BusType, Disk, Partition
from sysinstall.disks.identifiers import make_stable_id

_SUBPROCESS_TIMEOUT = 30  # PowerShell startup is slow

_BUS_MAP: dict[str, str] = {
    "usb": "usb",
    "sata": "sata",
    "nvme": "nvme",
    "scsi": "scsi",
    "ata": "sata",
    "raid": "scsi",
    "sas": "scsi",
    "fibre channel": "scsi",
    "iscsi": "scsi",
}


def _normalise_bus(bus_type: str | None) -> BusType:
    if not bus_type:
        return "unknown"
    return cast(BusType, _BUS_MAP.get(bus_type.lower().strip(), "unknown"))


def _ensure_list(obj: Any) -> list[Any]:
    """PowerShell ConvertTo-Json returns a single dict when there is only one item."""
    if obj is None:
        return []
    if isinstance(obj, list):
        return obj
    return [obj]


# ---------------------------------------------------------------------------
# Pure parsers — no subprocess; fully unit-testable.
# ---------------------------------------------------------------------------

def parse_powershell_disks(
    disk_json: bytes,
    partition_json: bytes,
    volume_json: bytes,
) -> list[Disk]:
    """Parse combined PowerShell JSON output into a list of :class:`Disk`.

    Args:
        disk_json:      Output of ``Get-Disk | ConvertTo-Json -Depth 5``.
        partition_json: Output of ``Get-Partition | ConvertTo-Json -Depth 5``.
        volume_json:    Output of ``Get-Volume | ConvertTo-Json -Depth 5``.
    """
    raw_disks = _ensure_list(json.loads(disk_json) if disk_json.strip() else [])
    raw_parts = _ensure_list(json.loads(partition_json) if partition_json.strip() else [])
    raw_vols = _ensure_list(json.loads(volume_json) if volume_json.strip() else [])

    # Build lookup: DriveLetter -> volume dict.
    vol_by_letter: dict[str, dict[str, Any]] = {}
    for vol in raw_vols:
        letter = vol.get("DriveLetter") or vol.get("UniqueId") or ""
        if letter:
            vol_by_letter[str(letter).upper()] = vol

    # Build lookup: disk_number -> list[partition dicts].
    parts_by_disk: dict[int, list[dict[str, Any]]] = {}
    for part in raw_parts:
        disk_num = int(part.get("DiskNumber", -1))
        if disk_num < 0:
            continue
        parts_by_disk.setdefault(disk_num, []).append(part)

    disks: list[Disk] = []
    for order, raw in enumerate(raw_disks):
        disk = _build_disk(raw, parts_by_disk, vol_by_letter, order)
        disks.append(disk)
    return disks


def _build_disk(
    raw: dict[str, Any],
    parts_by_disk: dict[int, list[dict[str, Any]]],
    vol_by_letter: dict[str, dict[str, Any]],
    order: int,
) -> Disk:
    disk_num = int(raw.get("DiskNumber", order))
    path = raw.get("Path") or f"\\\\.\\PhysicalDrive{disk_num}"
    size_bytes = int(raw.get("Size") or 0)
    model = (raw.get("Model") or raw.get("FriendlyName") or "Unknown").strip()
    serial: str | None = (raw.get("SerialNumber") or "").strip() or None

    bus_raw = raw.get("BusType") or raw.get("ProvisioningType") or ""
    bus = _normalise_bus(str(bus_raw))

    is_removable = str(raw.get("BusType") or "").lower() == "usb"
    is_system = bool(raw.get("IsBoot") or raw.get("IsSystem"))

    disk_parts = parts_by_disk.get(disk_num, [])
    partitions = _build_partitions(disk_parts, vol_by_letter)

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


def _build_partitions(
    raw_parts: list[dict[str, Any]],
    vol_by_letter: dict[str, dict[str, Any]],
) -> list[Partition]:
    parts: list[Partition] = []
    for part in raw_parts:
        drive_letter = str(part.get("DriveLetter") or "").upper()
        vol = vol_by_letter.get(drive_letter, {})

        mp = f"{drive_letter}:\\" if drive_letter else ""
        mps: tuple[str, ...] = (mp,) if mp else ()

        fs_type = vol.get("FileSystem") or part.get("Type") or None
        label = vol.get("FileSystemLabel") or None
        size_bytes = int(part.get("Size") or vol.get("Size") or 0)

        parts.append(Partition(
            id=str(part.get("Guid") or part.get("UniqueId") or ""),
            fs_type=fs_type,
            size_bytes=size_bytes,
            mountpoints=mps,
            label=label,
        ))
    return parts


# ---------------------------------------------------------------------------
# Subprocess wrapper
# ---------------------------------------------------------------------------

_PS_SCRIPT = (
    "Get-Disk | ConvertTo-Json -Depth 5; "
    "Write-Output '---PARTITION---'; "
    "Get-Partition | ConvertTo-Json -Depth 5; "
    "Write-Output '---VOLUME---'; "
    "Get-Volume | ConvertTo-Json -Depth 5"
)


def _run_powershell_combined() -> tuple[bytes, bytes, bytes]:
    """Run a single PowerShell session fetching disks, partitions, and volumes.

    Returns three byte strings: (disk_json, partition_json, volume_json).

    Raises:
        BackendUnavailable: if PowerShell is missing, times out, or exits non-zero.
    """
    cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS_SCRIPT]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=_SUBPROCESS_TIMEOUT,
        )
    except FileNotFoundError as exc:
        raise BackendUnavailable("powershell not found — not running on Windows?") from exc
    except subprocess.TimeoutExpired as exc:
        raise BackendUnavailable(f"PowerShell timed out after {_SUBPROCESS_TIMEOUT}s") from exc
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace").strip()
        raise BackendUnavailable(f"PowerShell exited {result.returncode}: {stderr}")

    stdout = result.stdout.decode(errors="replace")
    sections = stdout.split("---PARTITION---")
    disk_section = sections[0].strip().encode()
    rest = sections[1] if len(sections) > 1 else ""
    vol_sections = rest.split("---VOLUME---")
    partition_section = vol_sections[0].strip().encode()
    volume_section = vol_sections[1].strip().encode() if len(vol_sections) > 1 else b"[]"

    return disk_section, partition_section, volume_section


# ---------------------------------------------------------------------------
# Backend implementation
# ---------------------------------------------------------------------------

class WindowsBackend:
    """DiskBackend implementation for Windows using PowerShell."""

    def list_disks(self) -> list[Disk]:
        disk_json, partition_json, volume_json = _run_powershell_combined()
        return parse_powershell_disks(disk_json, partition_json, volume_json)

    def get_disk(self, disk_id: str) -> Disk:
        if not re.match(r"^[a-zA-Z0-9:.\-]+$", disk_id):
            raise KeyError(f"Invalid disk ID format: {disk_id!r}")
        for disk in self.list_disks():
            if disk.id == disk_id:
                return disk
        raise KeyError(f"Disk not found: {disk_id!r}")
