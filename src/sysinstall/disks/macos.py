"""macOS disk backend — uses diskutil(8) via subprocess + plistlib.

Architecture:
  - parse_diskutil_list(plist_bytes)  -> list[Disk]   pure function; unit-testable
  - _fetch_disk_info(dev_id)          -> dict          thin subprocess wrapper
  - MacOSBackend                      implements DiskBackend Protocol

Decision #6: iterate WholeDisks only; skip APFS synthesised containers.
System disk detection: any APFS volume with MountPoint == "/" on the disk.
"""

from __future__ import annotations

import plistlib
import subprocess
from typing import Any, cast

from sysinstall.disks.base import BackendUnavailable, BusType, Disk, Partition
from sysinstall.disks.identifiers import make_stable_id

# Timeout for each diskutil subprocess call (seconds).
_SUBPROCESS_TIMEOUT = 15

# Mapping from diskutil BusProtocol strings to normalised bus types.
_BUS_MAP: dict[str, str] = {
    "usb": "usb",
    "firewire": "usb",  # treat FW as removable/usb-class
    "thunderbolt": "usb",  # external Thunderbolt treated as usb-class
    "sata": "sata",
    "pcie": "nvme",
    "nvme": "nvme",
    "apple fabric": "nvme",  # Apple Silicon internal NVMe fabric
    "scsi": "scsi",
}


def _normalise_bus(raw: str) -> BusType:
    return cast(BusType, _BUS_MAP.get(raw.lower().strip(), "unknown"))


# ---------------------------------------------------------------------------
# Pure parser — never calls subprocess; fully unit-testable.
# ---------------------------------------------------------------------------

def parse_diskutil_list(plist_bytes: bytes) -> list[str]:
    """Parse `diskutil list -plist` output → list of whole-disk identifiers.

    Returns only identifiers listed under `WholeDisks` that are NOT APFS
    synthesized containers (decision #6). Synthesized containers are identified
    by having `APFSPhysicalStores` in their AllDisksAndPartitions entry —
    they represent virtual disks backed by a real GPT partition, not physical media.
    """
    data: dict[str, Any] = plistlib.loads(plist_bytes)
    whole_disks: list[str] = list(data.get("WholeDisks", []))

    # Build set of APFS container disk IDs to exclude.
    adp: list[dict[str, Any]] = data.get("AllDisksAndPartitions", [])
    apfs_containers: set[str] = {
        e["DeviceIdentifier"]
        for e in adp
        if "APFSPhysicalStores" in e and e.get("DeviceIdentifier")
    }

    return [d for d in whole_disks if d not in apfs_containers]


def parse_disk_info(info_bytes: bytes) -> dict[str, Any]:
    """Parse `diskutil info -plist <dev>` output → raw dict."""
    return dict(plistlib.loads(info_bytes))


def build_disk_from_info(
    info: dict[str, Any],
    apfs_volumes: list[dict[str, Any]],
    partitions_raw: list[dict[str, Any]],
    order: int,
) -> Disk:
    """Construct a :class:`Disk` from diskutil info dict + supplementary data.

    Args:
        info: Parsed output of ``diskutil info -plist <whole_disk>``.
        apfs_volumes: List of APFS volume dicts from ``AllDisksAndPartitions``
            for this disk (may be empty for non-APFS disks).
        partitions_raw: List of partition dicts from ``AllDisksAndPartitions``
            ``Partitions`` key (non-APFS layout).
        order: Zero-based enumeration index for fallback ID derivation.
    """
    dev_id: str = info.get("DeviceIdentifier", "")
    path: str = info.get("DeviceNode", f"/dev/{dev_id}")
    size_bytes: int = int(info.get("Size", info.get("TotalSize", 0)))
    model: str = (info.get("MediaName") or info.get("IORegistryEntryName") or "Unknown").strip()
    serial: str | None = info.get("IOSerialNumber") or None
    if serial:
        serial = serial.strip() or None

    raw_bus: str = info.get("BusProtocol", "")
    bus = _normalise_bus(raw_bus)

    is_removable: bool = bool(info.get("RemovableMediaOrExternalDevice", False))

    # System-disk detection: any APFS volume with MountPoint == "/"
    is_system = _detect_system_macos(apfs_volumes, partitions_raw)

    # Build partition list from APFS volumes + MBR/GPT partitions.
    parts = _build_partitions(apfs_volumes, partitions_raw)

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
        partitions=tuple(parts),
    )


def _detect_system_macos(
    apfs_volumes: list[dict[str, Any]],
    partitions_raw: list[dict[str, Any]],
) -> bool:
    """Return True if any volume/snapshot has MountPoint == '/'."""
    for vol in apfs_volumes:
        if vol.get("MountPoint") == "/":
            return True
        # Check mounted snapshots inside the volume.
        for snap in vol.get("MountedSnapshots", []):
            if snap.get("SnapshotMountPoint") == "/":
                return True
    return any(part.get("MountPoint") == "/" for part in partitions_raw)


def _build_partitions(
    apfs_volumes: list[dict[str, Any]],
    partitions_raw: list[dict[str, Any]],
) -> list[Partition]:
    parts: list[Partition] = []

    for vol in apfs_volumes:
        mp = vol.get("MountPoint", "") or ""
        mps: tuple[str, ...] = (mp,) if mp else ()
        parts.append(Partition(
            id=vol.get("DeviceIdentifier", ""),
            fs_type="apfs",
            size_bytes=int(vol.get("Size", 0)),
            mountpoints=mps,
            label=vol.get("VolumeName") or None,
        ))

    for part in partitions_raw:
        mp = part.get("MountPoint", "") or ""
        mps = (mp,) if mp else ()
        parts.append(Partition(
            id=part.get("DeviceIdentifier", ""),
            fs_type=part.get("Content") or None,
            size_bytes=int(part.get("Size", 0)),
            mountpoints=mps,
            label=None,
        ))

    return parts


# ---------------------------------------------------------------------------
# Subprocess wrappers — isolated; never called from unit tests.
# ---------------------------------------------------------------------------

def _run_diskutil(*args: str) -> bytes:
    """Run diskutil with *args*, return stdout bytes.

    Raises:
        BackendUnavailable: if diskutil is missing, times out, or exits non-zero.
    """
    cmd = ["diskutil", *args]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=_SUBPROCESS_TIMEOUT,
        )
    except FileNotFoundError as exc:
        raise BackendUnavailable("diskutil not found — not running on macOS?") from exc
    except subprocess.TimeoutExpired as exc:
        raise BackendUnavailable(f"diskutil timed out after {_SUBPROCESS_TIMEOUT}s") from exc
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace").strip()
        raise BackendUnavailable(f"diskutil exited {result.returncode}: {stderr}")
    return result.stdout


# ---------------------------------------------------------------------------
# Backend implementation
# ---------------------------------------------------------------------------

class MacOSBackend:
    """DiskBackend implementation for macOS using diskutil."""

    def list_disks(self) -> list[Disk]:
        """Enumerate whole physical disks via diskutil."""
        list_plist = _run_diskutil("list", "-plist")
        whole_disks = parse_diskutil_list(list_plist)

        # AllDisksAndPartitions includes both physical disks and APFS containers.
        all_data: dict[str, Any] = plistlib.loads(list_plist)
        adp: list[dict[str, Any]] = all_data.get("AllDisksAndPartitions", [])

        # Build lookup: device_id -> entry in AllDisksAndPartitions.
        adp_by_id: dict[str, dict[str, Any]] = {
            e.get("DeviceIdentifier", ""): e for e in adp
        }

        # Build map: physical partition dev_id -> APFS volumes in its container.
        # e.g. disk0s2 -> [volumes from disk3 container]
        partition_to_apfs_vols: dict[str, list[dict[str, Any]]] = {}
        for entry in adp:
            stores = entry.get("APFSPhysicalStores", [])
            vols = entry.get("APFSVolumes", [])
            if stores and vols:
                for store in stores:
                    store_id = store.get("DeviceIdentifier", "")
                    if store_id:
                        partition_to_apfs_vols.setdefault(store_id, []).extend(vols)

        disks: list[Disk] = []
        for order, dev_id in enumerate(whole_disks):
            try:
                info_bytes = _run_diskutil("info", "-plist", dev_id)
                info = parse_disk_info(info_bytes)
            except BackendUnavailable:
                continue

            entry = adp_by_id.get(dev_id, {})
            partitions_raw: list[dict[str, Any]] = entry.get("Partitions", [])

            # Collect APFS volumes from all containers backed by this disk's partitions.
            apfs_volumes: list[dict[str, Any]] = []
            for part in partitions_raw:
                part_id = part.get("DeviceIdentifier", "")
                apfs_volumes.extend(partition_to_apfs_vols.get(part_id, []))

            disk = build_disk_from_info(info, apfs_volumes, partitions_raw, order)
            disks.append(disk)

        return disks

    def get_disk(self, disk_id: str) -> Disk:
        """Re-resolve a disk by stable ID. Raises KeyError if not found."""
        import re
        if not re.match(r"^[a-zA-Z0-9:.\-]+$", disk_id):
            raise KeyError(f"Invalid disk ID format: {disk_id!r}")
        for disk in self.list_disks():
            if disk.id == disk_id:
                return disk
        raise KeyError(f"Disk not found: {disk_id!r}")
