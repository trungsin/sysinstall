"""Unit tests for the Linux lsblk JSON parser — no subprocess calls."""

from __future__ import annotations

from pathlib import Path

import pytest

from sysinstall.disks.linux import (
    _detect_system,
    _normalise_bus,
    parse_lsblk,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _lsblk_bytes() -> bytes:
    return (FIXTURES / "lsblk.json").read_bytes()


# ---------------------------------------------------------------------------
# _normalise_bus
# ---------------------------------------------------------------------------

class TestNormaliseBus:
    @pytest.mark.parametrize("raw,expected", [
        ("usb", "usb"),
        ("USB", "usb"),
        ("sata", "sata"),
        ("ata", "sata"),
        ("ide", "sata"),
        ("nvme", "nvme"),
        ("scsi", "scsi"),
        ("sas", "scsi"),
        (None, "unknown"),
        ("", "unknown"),
        ("fibre", "unknown"),
    ])
    def test_mapping(self, raw: str | None, expected: str) -> None:
        assert _normalise_bus(raw) == expected


# ---------------------------------------------------------------------------
# _detect_system
# ---------------------------------------------------------------------------

class TestDetectSystem:
    def test_root_mountpoint(self) -> None:
        children = [{"type": "part", "mountpoints": ["/"], "size": 1000}]
        assert _detect_system(children) is True

    def test_boot_efi_mountpoint(self) -> None:
        children = [{"type": "part", "mountpoints": ["/boot/efi"], "size": 1000}]
        assert _detect_system(children) is True

    def test_boot_mountpoint(self) -> None:
        children = [{"type": "part", "mountpoint": "/boot", "size": 1000}]
        assert _detect_system(children) is True

    def test_non_system_mountpoint(self) -> None:
        children = [{"type": "part", "mountpoints": ["/media/usb"], "size": 1000}]
        assert _detect_system(children) is False

    def test_empty(self) -> None:
        assert _detect_system([]) is False

    def test_null_mountpoints(self) -> None:
        children = [{"type": "part", "mountpoints": [None], "size": 1000}]
        assert _detect_system(children) is False


# ---------------------------------------------------------------------------
# parse_lsblk — fixture-based
# ---------------------------------------------------------------------------

class TestParseLsblk:
    def test_returns_two_disks(self) -> None:
        disks = parse_lsblk(_lsblk_bytes())
        assert len(disks) == 2

    def test_first_disk_is_sata(self) -> None:
        disks = parse_lsblk(_lsblk_bytes())
        sda = next(d for d in disks if d.path == "/dev/sda")
        assert sda.bus == "sata"

    def test_second_disk_is_usb_removable(self) -> None:
        disks = parse_lsblk(_lsblk_bytes())
        sdb = next(d for d in disks if d.path == "/dev/sdb")
        assert sdb.bus == "usb"
        assert sdb.is_removable is True

    def test_sda_is_system(self) -> None:
        disks = parse_lsblk(_lsblk_bytes())
        sda = next(d for d in disks if d.path == "/dev/sda")
        assert sda.is_system is True

    def test_sdb_not_system(self) -> None:
        disks = parse_lsblk(_lsblk_bytes())
        sdb = next(d for d in disks if d.path == "/dev/sdb")
        assert sdb.is_system is False

    def test_sda_has_three_partitions(self) -> None:
        disks = parse_lsblk(_lsblk_bytes())
        sda = next(d for d in disks if d.path == "/dev/sda")
        assert len(sda.partitions) == 3

    def test_sda_partition_mountpoints(self) -> None:
        disks = parse_lsblk(_lsblk_bytes())
        sda = next(d for d in disks if d.path == "/dev/sda")
        mps = {mp for p in sda.partitions for mp in p.mountpoints}
        assert "/" in mps
        assert "/boot" in mps
        assert "/boot/efi" in mps

    def test_stable_ids_differ_between_disks(self) -> None:
        disks = parse_lsblk(_lsblk_bytes())
        ids = [d.id for d in disks]
        assert ids[0] != ids[1]

    def test_stable_id_uses_serial(self) -> None:
        disks = parse_lsblk(_lsblk_bytes())
        sda = next(d for d in disks if d.path == "/dev/sda")
        assert "unstable" not in sda.id

    def test_disk_sizes(self) -> None:
        disks = parse_lsblk(_lsblk_bytes())
        sda = next(d for d in disks if d.path == "/dev/sda")
        assert sda.size_bytes == 512110190592

    def test_skips_non_disk_devices(self) -> None:
        """Partitions and loop devices in blockdevices are skipped."""
        import json
        data = {
            "blockdevices": [
                {"name": "/dev/sda", "path": "/dev/sda", "type": "disk", "size": "1000",
                 "model": "Test", "serial": "SN1", "tran": "sata", "rm": "0", "children": []},
                {"name": "/dev/loop0", "path": "/dev/loop0", "type": "loop", "size": "500",
                 "model": None, "serial": None, "tran": None, "rm": "0", "children": []},
            ]
        }
        disks = parse_lsblk(json.dumps(data).encode())
        assert len(disks) == 1
        assert disks[0].path == "/dev/sda"

    def test_disk_without_serial_gets_unstable_id(self) -> None:
        import json
        data = {
            "blockdevices": [
                {"name": "/dev/sda", "path": "/dev/sda", "type": "disk", "size": "1000000000",
                 "model": "NoSerial Disk", "serial": None, "tran": "sata", "rm": "0", "children": []},
            ]
        }
        disks = parse_lsblk(json.dumps(data).encode())
        assert disks[0].id.startswith("unstable:")
