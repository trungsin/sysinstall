"""Unit tests for the Windows PowerShell disk parser — no subprocess calls."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sysinstall.disks.windows import (
    _normalise_bus,
    parse_powershell_disks,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture() -> dict:
    return json.loads((FIXTURES / "powershell-disk.json").read_bytes())


def _fixture_bytes() -> tuple[bytes, bytes, bytes]:
    """Split the fixture JSON into (disk_json, partition_json, volume_json)."""
    raw = _load_fixture()
    disk_json = json.dumps(raw["disks"]).encode()
    partition_json = json.dumps(raw["partitions"]).encode()
    volume_json = json.dumps(raw["volumes"]).encode()
    return disk_json, partition_json, volume_json


# ---------------------------------------------------------------------------
# _normalise_bus
# ---------------------------------------------------------------------------

class TestNormaliseBus:
    @pytest.mark.parametrize("raw,expected", [
        ("USB", "usb"),
        ("usb", "usb"),
        ("NVMe", "nvme"),
        ("nvme", "nvme"),
        ("SATA", "sata"),
        ("ATA", "sata"),
        ("SCSI", "scsi"),
        ("SAS", "scsi"),
        (None, "unknown"),
        ("", "unknown"),
        ("iSCSI", "scsi"),
    ])
    def test_mapping(self, raw: str | None, expected: str) -> None:
        assert _normalise_bus(raw) == expected


# ---------------------------------------------------------------------------
# parse_powershell_disks — fixture-based
# ---------------------------------------------------------------------------

class TestParsePowershellDisks:
    def test_returns_two_disks(self) -> None:
        disks = parse_powershell_disks(*_fixture_bytes())
        assert len(disks) == 2

    def test_first_disk_is_nvme(self) -> None:
        disks = parse_powershell_disks(*_fixture_bytes())
        d0 = next(d for d in disks if "PhysicalDrive0" in d.path)
        assert d0.bus == "nvme"

    def test_first_disk_is_system(self) -> None:
        disks = parse_powershell_disks(*_fixture_bytes())
        d0 = next(d for d in disks if "PhysicalDrive0" in d.path)
        assert d0.is_system is True

    def test_second_disk_is_usb_removable(self) -> None:
        disks = parse_powershell_disks(*_fixture_bytes())
        d1 = next(d for d in disks if "PhysicalDrive1" in d.path)
        assert d1.bus == "usb"
        assert d1.is_removable is True

    def test_second_disk_not_system(self) -> None:
        disks = parse_powershell_disks(*_fixture_bytes())
        d1 = next(d for d in disks if "PhysicalDrive1" in d.path)
        assert d1.is_system is False

    def test_first_disk_has_three_partitions(self) -> None:
        disks = parse_powershell_disks(*_fixture_bytes())
        d0 = next(d for d in disks if "PhysicalDrive0" in d.path)
        assert len(d0.partitions) == 3

    def test_c_drive_partition_present(self) -> None:
        disks = parse_powershell_disks(*_fixture_bytes())
        d0 = next(d for d in disks if "PhysicalDrive0" in d.path)
        mps = {mp for p in d0.partitions for mp in p.mountpoints}
        assert "C:\\" in mps

    def test_usb_drive_partition_present(self) -> None:
        disks = parse_powershell_disks(*_fixture_bytes())
        d1 = next(d for d in disks if "PhysicalDrive1" in d.path)
        mps = {mp for p in d1.partitions for mp in p.mountpoints}
        assert "E:\\" in mps

    def test_partition_fs_type_from_volume(self) -> None:
        disks = parse_powershell_disks(*_fixture_bytes())
        d0 = next(d for d in disks if "PhysicalDrive0" in d.path)
        c_part = next(p for p in d0.partitions if "C:\\" in p.mountpoints)
        assert c_part.fs_type == "NTFS"

    def test_stable_id_with_serial(self) -> None:
        disks = parse_powershell_disks(*_fixture_bytes())
        d0 = next(d for d in disks if "PhysicalDrive0" in d.path)
        assert "unstable" not in d0.id

    def test_ids_differ_between_disks(self) -> None:
        disks = parse_powershell_disks(*_fixture_bytes())
        ids = [d.id for d in disks]
        assert ids[0] != ids[1]

    def test_disk_without_serial_gets_unstable_id(self) -> None:
        disk_json = json.dumps([{
            "DiskNumber": 0,
            "Path": "\\\\.\\PhysicalDrive0",
            "Model": "Mystery Disk",
            "SerialNumber": "",
            "Size": 1000000000,
            "BusType": "SATA",
            "IsBoot": False,
            "IsSystem": False,
        }]).encode()
        disks = parse_powershell_disks(disk_json, b"[]", b"[]")
        assert disks[0].id.startswith("unstable:")

    def test_single_disk_not_list_json(self) -> None:
        """PowerShell returns a single dict (not a list) when only one disk exists."""
        single = _load_fixture()["disks"][0]
        disk_json = json.dumps(single).encode()
        disks = parse_powershell_disks(disk_json, b"[]", b"[]")
        assert len(disks) == 1

    def test_empty_inputs(self) -> None:
        disks = parse_powershell_disks(b"[]", b"[]", b"[]")
        assert disks == []
