"""Unit tests for the macOS diskutil parser — no subprocess calls."""

from __future__ import annotations

from pathlib import Path

import pytest

from sysinstall.disks.macos import (
    _detect_system_macos,
    _normalise_bus,
    build_disk_from_info,
    parse_diskutil_list,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _plist_bytes() -> bytes:
    return (FIXTURES / "diskutil-plist.xml").read_bytes()


# ---------------------------------------------------------------------------
# parse_diskutil_list
# ---------------------------------------------------------------------------

class TestParseDiskutilList:
    def test_returns_only_physical_whole_disks(self) -> None:
        # disk1 in fixture is an APFS container (has APFSPhysicalStores) — excluded.
        ids = parse_diskutil_list(_plist_bytes())
        assert ids == ["disk0"]

    def test_excludes_partitions(self) -> None:
        ids = parse_diskutil_list(_plist_bytes())
        import re
        for d in ids:
            # Whole-disk identifiers match diskN; partitions match diskNsM
            assert re.match(r"^disk\d+$", d), f"Expected whole-disk id, got {d!r}"

    def test_empty_plist(self) -> None:
        import plistlib
        data = plistlib.dumps({"WholeDisks": [], "AllDisksAndPartitions": []})
        assert parse_diskutil_list(data) == []

    def test_no_whole_disks_key(self) -> None:
        import plistlib
        data = plistlib.dumps({"AllDisks": ["disk0"]})
        assert parse_diskutil_list(data) == []


# ---------------------------------------------------------------------------
# _normalise_bus
# ---------------------------------------------------------------------------

class TestNormaliseBus:
    @pytest.mark.parametrize("raw,expected", [
        ("Apple Fabric", "nvme"),
        ("apple fabric", "nvme"),
        ("PCIe", "nvme"),
        ("USB", "usb"),
        ("SATA", "sata"),
        ("SCSI", "scsi"),
        ("Thunderbolt", "usb"),
        ("FireWire", "usb"),
        ("unknown_bus", "unknown"),
        ("", "unknown"),
    ])
    def test_bus_mapping(self, raw: str, expected: str) -> None:
        assert _normalise_bus(raw) == expected


# ---------------------------------------------------------------------------
# _detect_system_macos
# ---------------------------------------------------------------------------

class TestDetectSystemMacos:
    def test_detects_root_mount_in_apfs_volume(self) -> None:
        vols = [{"DeviceIdentifier": "disk1s1", "MountPoint": "/", "MountedSnapshots": []}]
        assert _detect_system_macos(vols, []) is True

    def test_detects_root_via_snapshot(self) -> None:
        vols = [
            {
                "DeviceIdentifier": "disk1s1",
                "MountedSnapshots": [{"SnapshotMountPoint": "/"}],
            }
        ]
        assert _detect_system_macos(vols, []) is True

    def test_no_root_mount(self) -> None:
        vols = [{"DeviceIdentifier": "disk1s1", "MountPoint": "/System/Volumes/Data", "MountedSnapshots": []}]
        assert _detect_system_macos(vols, []) is False

    def test_root_in_gpt_partition(self) -> None:
        parts = [{"DeviceIdentifier": "disk0s2", "MountPoint": "/"}]
        assert _detect_system_macos([], parts) is True

    def test_empty(self) -> None:
        assert _detect_system_macos([], []) is False


# ---------------------------------------------------------------------------
# build_disk_from_info
# ---------------------------------------------------------------------------

class TestBuildDiskFromInfo:
    def _base_info(self) -> dict:
        return {
            "DeviceIdentifier": "disk0",
            "DeviceNode": "/dev/disk0",
            "Size": 500277792768,
            "TotalSize": 500277792768,
            "MediaName": "APPLE SSD AP0512Q",
            "IORegistryEntryName": "APPLE SSD AP0512Q Media",
            "BusProtocol": "Apple Fabric",
            "Internal": True,
            "Removable": False,
            "RemovableMediaOrExternalDevice": False,
        }

    def test_builds_system_disk(self) -> None:
        info = self._base_info()
        apfs_vols = [
            {
                "DeviceIdentifier": "disk3s1",
                "MountedSnapshots": [{"SnapshotMountPoint": "/"}],
                "Size": 494384795648,
                "VolumeName": "Macintosh HD",
            }
        ]
        disk = build_disk_from_info(info, apfs_vols, [], order=0)
        assert disk.is_system is True
        assert disk.path == "/dev/disk0"
        assert disk.model == "APPLE SSD AP0512Q"
        assert disk.bus == "nvme"
        assert disk.is_removable is False
        assert disk.size_bytes == 500277792768

    def test_builds_non_system_disk(self) -> None:
        info = self._base_info()
        info["RemovableMediaOrExternalDevice"] = True
        info["BusProtocol"] = "USB"
        disk = build_disk_from_info(info, [], [], order=1)
        assert disk.is_system is False
        assert disk.is_removable is True
        assert disk.bus == "usb"

    def test_stable_id_with_serial(self) -> None:
        info = self._base_info()
        info["IOSerialNumber"] = "TESTSN001"
        disk = build_disk_from_info(info, [], [], order=0)
        assert disk.id.startswith("nvme:")
        assert "unstable" not in disk.id

    def test_unstable_id_without_serial(self) -> None:
        info = self._base_info()
        # No IOSerialNumber key
        disk = build_disk_from_info(info, [], [], order=0)
        assert disk.id.startswith("unstable:")

    def test_partitions_populated(self) -> None:
        info = self._base_info()
        apfs_vols = [
            {"DeviceIdentifier": "disk1s1", "Size": 524288000, "VolumeName": "Macintosh HD", "MountPoint": "/"},
        ]
        raw_parts = [
            {"DeviceIdentifier": "disk0s1", "Content": "Apple_APFS_ISC", "Size": 524288000},
        ]
        disk = build_disk_from_info(info, apfs_vols, raw_parts, order=0)
        assert len(disk.partitions) == 2

    def test_empty_partitions_returns_empty_tuple(self) -> None:
        disk = build_disk_from_info(self._base_info(), [], [], order=0)
        assert disk.partitions == ()

    def test_id_stable_across_calls(self) -> None:
        info = self._base_info()
        info["IOSerialNumber"] = "STABLE_SERIAL"
        d1 = build_disk_from_info(info, [], [], order=0)
        d2 = build_disk_from_info(info, [], [], order=0)
        assert d1.id == d2.id

    def test_fixture_plist_whole_disks_count(self) -> None:
        """Smoke: fixture has 1 physical whole-disk after filtering APFS containers."""
        ids = parse_diskutil_list(_plist_bytes())
        assert len(ids) == 1

    def test_fixture_disk1_is_system(self) -> None:
        """disk1 in fixture has a snapshot mounted at /."""
        import plistlib
        data = plistlib.loads(_plist_bytes())
        adp = data["AllDisksAndPartitions"]
        disk1_entry = next(e for e in adp if e.get("DeviceIdentifier") == "disk1")
        apfs_vols = disk1_entry.get("APFSVolumes", [])
        assert _detect_system_macos(apfs_vols, []) is True
