"""Tests for ventoy.config.locked_rw — file lock round-trip on POSIX."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from sysinstall.iso.catalog import ManagedIso, add_to_catalog
from sysinstall.ventoy.config import locked_rw, read


def _setup_ventoy(tmp_path: Path, extra: dict | None = None) -> None:
    """Write a minimal ventoy.json with optional extra top-level keys."""
    ventoy_dir = tmp_path / "ventoy"
    ventoy_dir.mkdir(exist_ok=True)
    data: dict = {"_sysinstall": {"managed_by": "sysinstall", "managed_isos": []}}
    if extra:
        data.update(extra)
    (ventoy_dir / "ventoy.json").write_text(json.dumps(data), encoding="utf-8")


def _sample_iso(filename: str = "ubuntu.iso") -> ManagedIso:
    return ManagedIso(
        filename=filename,
        name="Ubuntu",
        sha256="b" * 64,
        size_bytes=999_000,
        added_at="2026-04-01T00:00:00+00:00",
    )


@pytest.mark.skipif(sys.platform == "win32", reason="fcntl not available on Windows")
class TestLockedRwPosix:
    def test_round_trip_writes_and_reads_back(self, tmp_path: Path) -> None:
        """locked_rw must write changes and be readable by subsequent read()."""
        _setup_ventoy(tmp_path)

        with locked_rw(tmp_path) as cfg:
            add_to_catalog(cfg, _sample_iso())

        restored = read(tmp_path)
        raw = json.loads((tmp_path / "ventoy" / "ventoy.json").read_text())
        assert len(raw["_sysinstall"]["managed_isos"]) == 1
        assert raw["_sysinstall"]["managed_isos"][0]["filename"] == "ubuntu.iso"

    def test_user_keys_preserved_through_locked_rw(self, tmp_path: Path) -> None:
        """User-set Ventoy keys survive a locked_rw cycle."""
        extra = {
            "control": [{"VTOY_DEFAULT_MENU_MODE": "0"}],
            "theme": {"file": "/ventoy/themes/dark/theme.txt"},
        }
        _setup_ventoy(tmp_path, extra=extra)

        with locked_rw(tmp_path) as cfg:
            add_to_catalog(cfg, _sample_iso())

        raw = json.loads((tmp_path / "ventoy" / "ventoy.json").read_text())
        assert raw.get("control") == extra["control"], "control key was clobbered"
        assert raw.get("theme") == extra["theme"], "theme key was clobbered"

    def test_exception_in_body_does_not_corrupt_file(self, tmp_path: Path) -> None:
        """If the body raises, the original ventoy.json must remain intact."""
        _setup_ventoy(tmp_path)

        original = (tmp_path / "ventoy" / "ventoy.json").read_text()

        with pytest.raises(RuntimeError, match="deliberate"), locked_rw(tmp_path) as cfg:
            add_to_catalog(cfg, _sample_iso())
            raise RuntimeError("deliberate failure")

        # File must still be parseable and unchanged (write happens after yield).
        current = (tmp_path / "ventoy" / "ventoy.json").read_text()
        assert json.loads(current) == json.loads(original)

    def test_sequential_locked_rw_accumulates(self, tmp_path: Path) -> None:
        """Two sequential locked_rw calls both commit their changes."""
        _setup_ventoy(tmp_path)

        with locked_rw(tmp_path) as cfg:
            add_to_catalog(cfg, _sample_iso("first.iso"))

        with locked_rw(tmp_path) as cfg:
            add_to_catalog(cfg, _sample_iso("second.iso"))

        raw = json.loads((tmp_path / "ventoy" / "ventoy.json").read_text())
        filenames = [e["filename"] for e in raw["_sysinstall"]["managed_isos"]]
        assert "first.iso" in filenames
        assert "second.iso" in filenames
