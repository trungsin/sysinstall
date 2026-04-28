"""Tests for the pure efibootmgr -v parser.

Uses the fixture at tests/boot/fixtures/efibootmgr-v.txt which contains
4 entries and a BootOrder line.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sysinstall.boot.efi import find_ubuntu_first_order, parse_efibootmgr
from sysinstall.boot.types import EfiEntry

FIXTURE = Path(__file__).parent / "fixtures" / "efibootmgr-v.txt"


@pytest.fixture()
def fixture_text() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_parse_returns_four_entries(fixture_text: str) -> None:
    entries = parse_efibootmgr(fixture_text)
    assert len(entries) == 4


def test_ubuntu_entry_active(fixture_text: str) -> None:
    entries = parse_efibootmgr(fixture_text)
    ubuntu = next(e for e in entries if "ubuntu" in e.label.lower())
    assert ubuntu.active is True
    assert ubuntu.num == "0001"


def test_windows_entry_active(fixture_text: str) -> None:
    entries = parse_efibootmgr(fixture_text)
    win = next(e for e in entries if "Windows" in e.label)
    assert win.active is True
    assert win.num == "0002"


def test_boot_order_positions(fixture_text: str) -> None:
    """BootOrder: 0001,0002,0003,0000 => positions 0,1,2,3."""
    entries = parse_efibootmgr(fixture_text)
    by_num = {e.num: e for e in entries}
    assert by_num["0001"].boot_order_position == 0
    assert by_num["0002"].boot_order_position == 1
    assert by_num["0003"].boot_order_position == 2
    assert by_num["0000"].boot_order_position == 3


def test_inactive_entry_has_no_asterisk(fixture_text: str) -> None:
    entries = parse_efibootmgr(fixture_text)
    hd = next(e for e in entries if e.num == "0000")
    assert hd.active is False


def test_efi_path_captured(fixture_text: str) -> None:
    entries = parse_efibootmgr(fixture_text)
    ubuntu = next(e for e in entries if e.num == "0001")
    assert "shimx64.efi" in ubuntu.path


def test_parse_empty_string() -> None:
    entries = parse_efibootmgr("")
    assert entries == []


def test_parse_no_boot_order() -> None:
    text = "Boot0001* ubuntu\tHD(...)\n"
    entries = parse_efibootmgr(text)
    assert len(entries) == 1
    assert entries[0].boot_order_position == -1


def test_find_ubuntu_first_order_moves_ubuntu() -> None:
    entries = [
        EfiEntry(num="0002", label="Windows Boot Manager", path="", active=True),
        EfiEntry(num="0001", label="ubuntu", path="", active=True),
        EfiEntry(num="0003", label="PXE", path="", active=False),
    ]
    result = find_ubuntu_first_order(entries)
    assert result[0].label == "ubuntu"
    assert [e.num for e in result] == ["0001", "0002", "0003"]


def test_find_ubuntu_first_order_no_ubuntu() -> None:
    entries = [
        EfiEntry(num="0002", label="Windows Boot Manager", path="", active=True),
        EfiEntry(num="0003", label="PXE", path="", active=False),
    ]
    result = find_ubuntu_first_order(entries)
    # unchanged order
    assert [e.num for e in result] == ["0002", "0003"]
