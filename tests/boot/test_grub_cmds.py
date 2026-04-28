"""Tests for grub command builders (pure functions, no subprocess).

Verifies that install_uefi, install_bios, update_grub produce the
expected subprocess argument lists without actually calling subprocess.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sysinstall.boot.grub import (
    _bios_install_args,
    _uefi_install_args,
    _update_grub_args,
    install_bios,
    install_uefi,
    update_grub,
)

CHROOT = Path("/tmp/sysinstall-chroot-test")
DISK = Path("/dev/sda")


# ---------------------------------------------------------------------------
# Pure builder tests (no subprocess)
# ---------------------------------------------------------------------------


def test_uefi_install_args_structure() -> None:
    args = _uefi_install_args(CHROOT)
    assert args[0] == "chroot"
    assert args[1] == str(CHROOT)
    assert "grub-install" in args
    assert "--target=x86_64-efi" in args
    assert "--efi-directory=/boot/efi" in args
    assert "--bootloader-id=ubuntu" in args


def test_bios_install_args_structure() -> None:
    args = _bios_install_args(CHROOT, DISK)
    assert args[0] == "chroot"
    assert "--target=i386-pc" in args
    assert str(DISK) in args


def test_update_grub_args_structure() -> None:
    args = _update_grub_args(CHROOT)
    assert "chroot" in args
    assert "update-grub" in args
    assert str(CHROOT) in args


# ---------------------------------------------------------------------------
# Execution tests (mocked subprocess)
# ---------------------------------------------------------------------------


@patch("sysinstall.boot.grub.subprocess.run")
def test_install_uefi_calls_correct_args(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")
    install_uefi(CHROOT, dry_run=False)
    called_args = mock_run.call_args[0][0]
    assert "grub-install" in called_args
    assert "--target=x86_64-efi" in called_args


@patch("sysinstall.boot.grub.subprocess.run")
def test_install_bios_calls_correct_args(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")
    install_bios(CHROOT, DISK, dry_run=False)
    called_args = mock_run.call_args[0][0]
    assert "--target=i386-pc" in called_args
    assert str(DISK) in called_args


@patch("sysinstall.boot.grub.subprocess.run")
def test_update_grub_calls_correct_args(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")
    update_grub(CHROOT, dry_run=False)
    called_args = mock_run.call_args[0][0]
    assert "update-grub" in called_args


@patch("sysinstall.boot.grub.subprocess.run")
def test_install_uefi_raises_on_nonzero(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=1, stdout=b"", stderr=b"grub error")
    with pytest.raises(RuntimeError, match="failed"):
        install_uefi(CHROOT, dry_run=False)


def test_install_uefi_dry_run_no_subprocess() -> None:
    """dry_run=True must not call subprocess at all."""
    with patch("sysinstall.boot.grub.subprocess.run") as mock_run:
        install_uefi(CHROOT, dry_run=True)
        mock_run.assert_not_called()


def test_install_bios_dry_run_no_subprocess() -> None:
    with patch("sysinstall.boot.grub.subprocess.run") as mock_run:
        install_bios(CHROOT, DISK, dry_run=True)
        mock_run.assert_not_called()
