"""Tests for the boot environment detector.

Uses SYSINSTALL_FIRMWARE env var to override firmware detection.
Mocks list_disks() to return a canonical 3-partition VM layout:
  - /dev/sda1: vfat  (ESP)
  - /dev/sda2: ntfs  (Windows)
  - /dev/sda3: ext4  (Ubuntu root)
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from sysinstall.boot.detector import (
    _is_esp_candidate,
    _is_linux_root_candidate,
    _is_windows_candidate,
    find_candidates,
    is_uefi,
)
from sysinstall.disks.base import Disk, Partition


def _make_partition(
    part_id: str,
    fs_type: str | None,
    size_bytes: int = 10 * 1024**3,
    label: str | None = None,
) -> Partition:
    return Partition(
        id=part_id,
        fs_type=fs_type,
        size_bytes=size_bytes,
        mountpoints=(),
        label=label,
    )


def _make_vm_disk() -> Disk:
    """3-partition VM disk: ESP + Windows + Ubuntu root."""
    return Disk(
        id="sata:VM001:32212254720",
        path="/dev/sda",
        size_bytes=32 * 1024**3,
        model="VBOX HARDDISK",
        serial="VM001",
        bus="sata",
        is_removable=False,
        is_system=False,
        partitions=(
            _make_partition("/dev/sda1", "vfat", 512 * 1024**2, "EFI"),
            _make_partition("/dev/sda2", "ntfs", 20 * 1024**3, "Windows"),
            _make_partition("/dev/sda3", "ext4", 10 * 1024**3, "Ubuntu"),
        ),
    )


# ---------------------------------------------------------------------------
# is_uefi tests
# ---------------------------------------------------------------------------


def test_is_uefi_env_override_uefi(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYSINSTALL_FIRMWARE", "uefi")
    assert is_uefi() is True


def test_is_uefi_env_override_bios(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYSINSTALL_FIRMWARE", "bios")
    assert is_uefi() is False


def test_is_uefi_returns_false_on_non_linux() -> None:
    import sys
    with patch.object(sys, "platform", "darwin"):
        # Clear any env override
        with patch.dict("os.environ", {"SYSINSTALL_FIRMWARE": ""}, clear=False):
            # On non-linux without env override -> False
            result = is_uefi()
    assert result is False


# ---------------------------------------------------------------------------
# Partition classifier tests
# ---------------------------------------------------------------------------


def test_esp_candidate_vfat() -> None:
    p = _make_partition("/dev/sda1", "vfat")
    assert _is_esp_candidate(p) is True


def test_esp_candidate_fat32() -> None:
    p = _make_partition("/dev/sda1", "fat32")
    assert _is_esp_candidate(p) is True


def test_esp_candidate_ext4_is_not_esp() -> None:
    p = _make_partition("/dev/sda3", "ext4")
    assert _is_esp_candidate(p) is False


def test_linux_root_candidate_ext4() -> None:
    p = _make_partition("/dev/sda3", "ext4")
    assert _is_linux_root_candidate(p) is True


def test_linux_root_candidate_btrfs() -> None:
    p = _make_partition("/dev/sda3", "btrfs")
    assert _is_linux_root_candidate(p) is True


def test_windows_candidate_ntfs() -> None:
    p = _make_partition("/dev/sda2", "ntfs")
    assert _is_windows_candidate(p) is True


def test_windows_candidate_fat32_is_not_windows() -> None:
    p = _make_partition("/dev/sda1", "fat32")
    assert _is_windows_candidate(p) is False


# ---------------------------------------------------------------------------
# find_candidates integration test (mocked list_disks)
# ---------------------------------------------------------------------------


def test_find_candidates_classifies_vm_disk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYSINSTALL_FIRMWARE", "uefi")
    disk = _make_vm_disk()

    with patch("sysinstall.boot.detector._get_efi_entries_if_uefi", return_value=()):
        env = find_candidates(disks=[disk])

    assert env.firmware == "uefi"
    assert len(env.candidate_efi) == 1
    assert env.candidate_efi[0].id == "/dev/sda1"
    assert len(env.candidate_linux_roots) == 1
    assert env.candidate_linux_roots[0].id == "/dev/sda3"
    assert len(env.candidate_windows) == 1
    assert env.candidate_windows[0].id == "/dev/sda2"


def test_find_candidates_bios_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYSINSTALL_FIRMWARE", "bios")
    disk = _make_vm_disk()

    with patch("sysinstall.boot.detector._get_efi_entries_if_uefi", return_value=()):
        env = find_candidates(disks=[disk])

    assert env.firmware == "bios"
    assert env.efi_entries == ()


def test_find_candidates_empty_disk_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYSINSTALL_FIRMWARE", "uefi")
    with patch("sysinstall.boot.detector._get_efi_entries_if_uefi", return_value=()):
        env = find_candidates(disks=[])
    assert env.candidate_efi == ()
    assert env.candidate_linux_roots == ()
    assert env.candidate_windows == ()
