"""Tests for ventoy.json read/write round-trip and unknown-key preservation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sysinstall.ventoy.config import ManagedIso, VentoyConfig, make_skeleton, read, write


def _write_raw(tmp_path: Path, data: dict) -> Path:
    cfg_dir = tmp_path / "ventoy"
    cfg_dir.mkdir()
    cfg_file = cfg_dir / "ventoy.json"
    cfg_file.write_text(json.dumps(data), encoding="utf-8")
    return tmp_path


class TestMakeSkeleton:
    def test_returns_ventoy_config(self):
        cfg = make_skeleton()
        assert isinstance(cfg, VentoyConfig)

    def test_managed_isos_empty(self):
        cfg = make_skeleton()
        assert cfg.managed_isos == []

    def test_raw_contains_sysinstall_key(self):
        cfg = make_skeleton()
        assert "_sysinstall" in cfg._raw


class TestWriteAndRead:
    def test_round_trip_empty_config(self, tmp_path: Path):
        cfg = make_skeleton()
        write(tmp_path, cfg)
        restored = read(tmp_path)
        assert restored.managed_isos == []

    def test_round_trip_with_isos(self, tmp_path: Path):
        cfg = make_skeleton()
        cfg.managed_isos.append(
            ManagedIso(filename="ubuntu.iso", label="Ubuntu", added_ts="2026-01-01T00:00:00+00:00")
        )
        write(tmp_path, cfg)
        restored = read(tmp_path)
        assert len(restored.managed_isos) == 1
        assert restored.managed_isos[0].filename == "ubuntu.iso"
        assert restored.managed_isos[0].label == "Ubuntu"

    def test_preserves_unknown_top_level_keys(self, tmp_path: Path):
        """User-set keys like 'control', 'theme' must survive a sysinstall write."""
        existing = {
            "control": [{"VTOY_DEFAULT_MENU_MODE": "0"}],
            "theme": {"file": "/ventoy/themes/default/theme.txt"},
            "_sysinstall": {"managed_by": "sysinstall", "managed_isos": []},
        }
        _write_raw(tmp_path, existing)

        cfg = read(tmp_path)
        cfg.managed_isos.append(
            ManagedIso(filename="arch.iso", label="Arch Linux", added_ts="2026-01-01T00:00:00+00:00")
        )
        write(tmp_path, cfg)

        raw = json.loads((tmp_path / "ventoy" / "ventoy.json").read_text())
        assert "control" in raw, "user 'control' key was clobbered"
        assert raw["control"] == existing["control"]
        assert "theme" in raw, "user 'theme' key was clobbered"
        assert raw["theme"] == existing["theme"]

    def test_sysinstall_namespace_is_overwritten(self, tmp_path: Path):
        """The _sysinstall key is always managed by sysinstall, never stale."""
        existing = {
            "_sysinstall": {
                "managed_by": "sysinstall",
                "managed_isos": [
                    {"filename": "old.iso", "label": "Old", "added_ts": "2025-01-01T00:00:00+00:00"}
                ],
            }
        }
        _write_raw(tmp_path, existing)

        cfg = read(tmp_path)
        assert len(cfg.managed_isos) == 1
        cfg.managed_isos.clear()
        write(tmp_path, cfg)

        raw = json.loads((tmp_path / "ventoy" / "ventoy.json").read_text())
        assert raw["_sysinstall"]["managed_isos"] == []

    def test_creates_ventoy_dir_if_missing(self, tmp_path: Path):
        cfg = make_skeleton()
        write(tmp_path, cfg)
        assert (tmp_path / "ventoy" / "ventoy.json").exists()

    def test_read_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            read(tmp_path)

    def test_written_file_is_valid_json(self, tmp_path: Path):
        write(tmp_path, make_skeleton())
        content = (tmp_path / "ventoy" / "ventoy.json").read_text()
        parsed = json.loads(content)
        assert isinstance(parsed, dict)
