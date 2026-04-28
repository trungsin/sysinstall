"""Tests for JSONL audit logger: append, rotation, retention."""

from __future__ import annotations

import json
from pathlib import Path

from sysinstall.safety.audit import append_audit


def _read_entries(log_path: Path) -> list[dict]:
    return [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]


class TestAppendAudit:
    def test_creates_file_on_first_write(self, tmp_path: Path):
        append_audit("usb_create", "disk:test:1", "started", state_dir=tmp_path)
        log_file = tmp_path / "audit.jsonl"
        assert log_file.exists()

    def test_entry_has_required_fields(self, tmp_path: Path):
        append_audit(
            "usb_create",
            "disk:test:1",
            "success",
            args={"dry_run": True},
            state_dir=tmp_path,
        )
        entries = _read_entries(tmp_path / "audit.jsonl")
        assert len(entries) == 1
        e = entries[0]
        assert e["action"] == "usb_create"
        assert e["target"] == "disk:test:1"
        assert e["outcome"] == "success"
        assert e["args"] == {"dry_run": True}
        assert e["error"] is None
        assert "ts" in e
        assert "actor" in e

    def test_multiple_appends(self, tmp_path: Path):
        for outcome in ("started", "success"):
            append_audit("usb_create", "disk:1", outcome, state_dir=tmp_path)
        entries = _read_entries(tmp_path / "audit.jsonl")
        assert len(entries) == 2
        assert entries[0]["outcome"] == "started"
        assert entries[1]["outcome"] == "success"

    def test_error_field_populated(self, tmp_path: Path):
        append_audit(
            "usb_create", "disk:1", "failure",
            error="Something went wrong",
            state_dir=tmp_path,
        )
        entries = _read_entries(tmp_path / "audit.jsonl")
        assert entries[0]["error"] == "Something went wrong"

    def test_dry_run_outcome(self, tmp_path: Path):
        append_audit("usb_create", "disk:1", "dry_run", state_dir=tmp_path)
        entries = _read_entries(tmp_path / "audit.jsonl")
        assert entries[0]["outcome"] == "dry_run"

    def test_each_line_is_valid_json(self, tmp_path: Path):
        for i in range(5):
            append_audit("action", f"disk:{i}", "success", state_dir=tmp_path)
        log_file = tmp_path / "audit.jsonl"
        for line in log_file.read_text().splitlines():
            json.loads(line)  # must not raise


class TestAuditRotation:
    def test_rotation_triggers_at_threshold(self, tmp_path: Path):
        """When log exceeds max_bytes, it is renamed to .1 and a new file starts."""
        log_file = tmp_path / "audit.jsonl"
        # Write enough data to exceed a tiny threshold.
        log_file.write_text("x" * 200, encoding="utf-8")

        append_audit(
            "test_action", "disk:1", "success",
            state_dir=tmp_path,
            max_bytes=100,  # tiny threshold
            keep=5,
        )

        backup = tmp_path / "audit.jsonl.1"
        assert backup.exists(), "audit.jsonl.1 backup should exist after rotation"
        assert log_file.exists(), "new audit.jsonl should exist after rotation"

        # New log should contain the fresh entry only.
        entries = _read_entries(log_file)
        assert len(entries) == 1
        assert entries[0]["action"] == "test_action"

    def test_rotation_keeps_at_most_keep_backups(self, tmp_path: Path):
        """Old backups beyond 'keep' are deleted."""
        log_file = tmp_path / "audit.jsonl"

        # Pre-create 5 backups (.1 through .5).
        for i in range(1, 6):
            (tmp_path / f"audit.jsonl.{i}").write_text(f"backup-{i}", encoding="utf-8")

        # Fill active log to exceed threshold.
        log_file.write_text("x" * 200, encoding="utf-8")

        append_audit(
            "rotate_test", "disk:1", "started",
            state_dir=tmp_path,
            max_bytes=100,
            keep=5,
        )

        # .5 should have been deleted, .1-.4 shifted to .2-.5, active -> .1.
        assert not (tmp_path / "audit.jsonl.6").exists(), "No .6 file should exist"
        assert (tmp_path / "audit.jsonl.1").exists()
        assert (tmp_path / "audit.jsonl.5").exists()

    def test_no_rotation_below_threshold(self, tmp_path: Path):
        """Log is not rotated if smaller than max_bytes."""
        log_file = tmp_path / "audit.jsonl"
        log_file.write_text("small", encoding="utf-8")

        append_audit(
            "noop", "disk:1", "success",
            state_dir=tmp_path,
            max_bytes=10 * 1024 * 1024,  # 10 MiB — will not trigger
            keep=5,
        )

        assert not (tmp_path / "audit.jsonl.1").exists(), "Should not rotate"

    def test_rotation_shifts_existing_backups(self, tmp_path: Path):
        """Existing .1 is moved to .2, .2 to .3, etc."""
        log_file = tmp_path / "audit.jsonl"
        (tmp_path / "audit.jsonl.1").write_text("old-1", encoding="utf-8")
        (tmp_path / "audit.jsonl.2").write_text("old-2", encoding="utf-8")
        log_file.write_text("x" * 200, encoding="utf-8")

        append_audit(
            "shift_test", "disk:1", "success",
            state_dir=tmp_path,
            max_bytes=100,
            keep=5,
        )

        assert (tmp_path / "audit.jsonl.2").read_text() == "old-1"
        assert (tmp_path / "audit.jsonl.3").read_text() == "old-2"
