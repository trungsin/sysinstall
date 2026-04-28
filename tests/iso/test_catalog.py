"""Tests for iso.catalog — round-trip, key preservation, add/remove/find."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sysinstall.iso.catalog import (
    ManagedIso,
    add_to_catalog,
    find_in_catalog,
    list_catalog,
    remove_from_catalog,
    validate_filename,
)
from sysinstall.ventoy.config import make_skeleton, read, write


def _write_raw(tmp_path: Path, data: dict) -> None:
    cfg_dir = tmp_path / "ventoy"
    cfg_dir.mkdir(exist_ok=True)
    (cfg_dir / "ventoy.json").write_text(json.dumps(data), encoding="utf-8")


def _sample_iso(filename: str = "ubuntu-24.04.iso") -> ManagedIso:
    return ManagedIso(
        filename=filename,
        name="Ubuntu 24.04",
        sha256="a" * 64,
        size_bytes=1_000_000,
        added_at="2026-01-01T00:00:00+00:00",
    )


class TestValidateFilename:
    def test_valid_names(self) -> None:
        for name in ["ubuntu-24.04.iso", "WIN_11_22H2.ISO", "arch linux 2026.iso"]:
            validate_filename(name)  # must not raise

    def test_reject_dotdot(self) -> None:
        with pytest.raises(ValueError, match="disallowed sequence"):
            validate_filename("../etc/passwd.iso")

    def test_reject_forward_slash(self) -> None:
        with pytest.raises(ValueError, match="disallowed sequence"):
            validate_filename("name/slash.iso")

    def test_reject_backslash(self) -> None:
        with pytest.raises(ValueError, match="disallowed sequence"):
            validate_filename("name\\back.iso")

    def test_reject_no_iso_extension(self) -> None:
        with pytest.raises(ValueError, match="allowed pattern"):
            validate_filename("ubuntu.img")

    def test_reject_absolute_path(self) -> None:
        # Forward slash triggers the slash check first.
        with pytest.raises(ValueError):
            validate_filename("/abs.iso")


class TestAddRemoveFind:
    def test_add_and_find_by_filename(self, tmp_path: Path) -> None:
        cfg = make_skeleton()
        iso = _sample_iso()
        add_to_catalog(cfg, iso)
        found = find_in_catalog(cfg, "ubuntu-24.04.iso")
        assert found is not None
        assert found.sha256 == iso.sha256

    def test_find_by_name(self, tmp_path: Path) -> None:
        cfg = make_skeleton()
        iso = _sample_iso()
        add_to_catalog(cfg, iso)
        found = find_in_catalog(cfg, "Ubuntu 24.04")
        assert found is not None
        assert found.filename == "ubuntu-24.04.iso"

    def test_find_missing_returns_none(self) -> None:
        cfg = make_skeleton()
        assert find_in_catalog(cfg, "nonexistent.iso") is None

    def test_remove_by_filename(self) -> None:
        cfg = make_skeleton()
        iso = _sample_iso()
        add_to_catalog(cfg, iso)
        removed = remove_from_catalog(cfg, "ubuntu-24.04.iso")
        assert removed.filename == "ubuntu-24.04.iso"
        assert find_in_catalog(cfg, "ubuntu-24.04.iso") is None

    def test_remove_missing_raises_key_error(self) -> None:
        cfg = make_skeleton()
        with pytest.raises(KeyError):
            remove_from_catalog(cfg, "ghost.iso")

    def test_list_catalog_empty(self) -> None:
        cfg = make_skeleton()
        assert list_catalog(cfg) == []

    def test_list_catalog_multiple(self) -> None:
        cfg = make_skeleton()
        add_to_catalog(cfg, _sample_iso("a.iso"))
        add_to_catalog(cfg, _sample_iso("b.iso"))
        entries = list_catalog(cfg)
        assert len(entries) == 2
        assert {e.filename for e in entries} == {"a.iso", "b.iso"}


class TestRoundTripPreservesUserKeys:
    def test_ventoy_plugin_keys_survive_catalog_write(self, tmp_path: Path) -> None:
        """User-set Ventoy plugin keys must not be clobbered by sysinstall writes."""
        existing = {
            "control": [{"VTOY_DEFAULT_MENU_MODE": "0"}],
            "theme": {"file": "/ventoy/themes/default/theme.txt"},
            "auto_install": [{"image": "/ubuntu.iso"}],
            "_sysinstall": {"managed_by": "sysinstall", "managed_isos": []},
        }
        _write_raw(tmp_path, existing)

        cfg = read(tmp_path)
        add_to_catalog(cfg, _sample_iso())
        write(tmp_path, cfg)

        raw = json.loads((tmp_path / "ventoy" / "ventoy.json").read_text())
        assert raw.get("control") == existing["control"], "control key clobbered"
        assert raw.get("theme") == existing["theme"], "theme key clobbered"
        assert raw.get("auto_install") == existing["auto_install"], "auto_install key clobbered"

    def test_managed_isos_persisted(self, tmp_path: Path) -> None:
        cfg = make_skeleton()
        add_to_catalog(cfg, _sample_iso())
        write(tmp_path, cfg)

        restored = read(tmp_path)
        entries = list_catalog(restored)
        assert len(entries) == 1
        assert entries[0].filename == "ubuntu-24.04.iso"
