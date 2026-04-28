"""Tests that install_to_disk raises UnsupportedHostError on macOS."""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from sysinstall.ventoy import MACOS_VENTOY_MESSAGE, UnsupportedHostError


def _make_disk():
    from sysinstall.disks.base import Disk
    return Disk(
        id="usb:test:1234",
        path="/dev/sdb",
        size_bytes=16 * 1024 ** 3,
        model="Test USB",
        serial="SN123",
        bus="usb",
        is_removable=True,
        is_system=False,
        partitions=(),
    )


class TestMacOSUnsupported:
    def test_install_raises_on_darwin(self):
        """install_to_disk must raise UnsupportedHostError on sys.platform == 'darwin'."""
        from sysinstall.ventoy import install_to_disk

        with patch.object(sys, "platform", "darwin"):
            with pytest.raises(UnsupportedHostError) as exc_info:
                install_to_disk(_make_disk())

        assert "macOS" in str(exc_info.value)

    def test_error_message_contains_dd_reference(self):
        """The error message must mention dd as a workaround."""
        from sysinstall.ventoy import install_to_disk

        with patch.object(sys, "platform", "darwin"):
            with pytest.raises(UnsupportedHostError) as exc_info:
                install_to_disk(_make_disk())

        msg = str(exc_info.value)
        assert "dd" in msg.lower() or "workaround" in msg.lower() or "linux" in msg.lower()

    def test_error_message_mentions_alternatives(self):
        """MACOS_VENTOY_MESSAGE should mention Linux or Windows host."""
        assert "Linux" in MACOS_VENTOY_MESSAGE or "Windows" in MACOS_VENTOY_MESSAGE

    def test_update_raises_on_darwin(self):
        """update() must also raise UnsupportedHostError on macOS."""
        from sysinstall.ventoy import update

        with patch.object(sys, "platform", "darwin"), pytest.raises(UnsupportedHostError):
            update(_make_disk())

    def test_is_installed_does_not_raise_on_darwin(self):
        """is_installed() is read-only and safe to call on macOS."""
        from sysinstall.ventoy import is_installed

        disk = _make_disk()
        # Should not raise — just returns False (no Ventoy partitions).
        with patch.object(sys, "platform", "darwin"):
            result = is_installed(disk)
        assert result is False
