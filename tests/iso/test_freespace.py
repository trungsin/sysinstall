"""Tests for free-space pre-check in iso.__init__.add_iso."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sysinstall.disks.base import Disk, Partition
from sysinstall.iso import add_iso
from sysinstall.iso.errors import InsufficientSpaceError


def _make_disk(mount: str) -> Disk:
    """Return a minimal Disk fixture with one mounted partition."""
    partition = Partition(
        id="part0",
        fs_type="exfat",
        size_bytes=32 * 1024 ** 3,
        mountpoints=(mount,),
        label="VENTOY",
    )
    return Disk(
        id="usb:TEST:123",
        path="/dev/sdb",
        size_bytes=32 * 1024 ** 3,
        model="Test USB",
        serial="TESTSERIAL",
        bus="usb",
        is_removable=True,
        is_system=False,
        partitions=(partition,),
    )


def _setup_ventoy_mount(tmp_path: Path) -> None:
    """Create a minimal ventoy.json so resolve_usb_mount passes."""
    ventoy_dir = tmp_path / "ventoy"
    ventoy_dir.mkdir()
    (ventoy_dir / "ventoy.json").write_text(
        json.dumps({"_sysinstall": {"managed_by": "sysinstall", "managed_isos": []}}),
        encoding="utf-8",
    )


class TestFreeSpacePrecheck:
    def test_raises_insufficient_space_error(self, tmp_path: Path) -> None:
        """InsufficientSpaceError must be raised when free < iso_size + 50 MiB."""
        _setup_ventoy_mount(tmp_path)
        disk = _make_disk(str(tmp_path))

        iso_file = tmp_path / "test.iso"
        iso_size = 4 * 1024 ** 3  # 4 GiB
        iso_file.write_bytes(b"\x00" * 100)  # tiny stand-in; stat() size is mocked

        headroom = 50 * 1024 * 1024
        available = iso_size + headroom - 1  # one byte short

        stat_result = MagicMock()
        stat_result.st_size = iso_size

        disk_usage_result = MagicMock()
        disk_usage_result.free = available

        with (
            patch("sysinstall.iso.copy.stream_copy"),
            patch("pathlib.Path.stat", return_value=stat_result),
            patch("sysinstall.iso.mount_resolver.shutil.disk_usage", return_value=disk_usage_result),
        ):
            with pytest.raises(InsufficientSpaceError) as exc_info:
                add_iso(disk, iso_file)

        err = exc_info.value
        assert err.required == iso_size + headroom
        assert err.available == available

    def test_passes_when_space_sufficient(self, tmp_path: Path) -> None:
        """No error raised when free space is exactly iso_size + 50 MiB."""
        _setup_ventoy_mount(tmp_path)
        disk = _make_disk(str(tmp_path))

        iso_size = 1 * 1024 ** 3  # 1 GiB
        headroom = 50 * 1024 * 1024
        available = iso_size + headroom  # exactly enough

        src_iso = tmp_path / "ubuntu.iso"
        src_iso.write_bytes(b"\x00" * 100)

        stat_result = MagicMock()
        stat_result.st_size = iso_size

        disk_usage_result = MagicMock()
        disk_usage_result.free = available

        copied_sha = "a" * 64

        with (
            patch("pathlib.Path.stat", return_value=stat_result),
            patch("sysinstall.iso.mount_resolver.shutil.disk_usage", return_value=disk_usage_result),
            patch("sysinstall.iso.stream_copy", return_value=(iso_size, copied_sha)),
            patch("sysinstall.iso.ventoy_config.locked_rw") as mock_lrw,
            patch("sysinstall.iso.append_audit"),
        ):
            from sysinstall.ventoy.config import make_skeleton
            mock_cfg = make_skeleton()
            mock_lrw.return_value.__enter__ = MagicMock(return_value=mock_cfg)
            mock_lrw.return_value.__exit__ = MagicMock(return_value=False)

            result = add_iso(disk, src_iso)

        assert result.filename == "ubuntu.iso"
