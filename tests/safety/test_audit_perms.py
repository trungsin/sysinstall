"""Tests for audit log file permissions (0600 on POSIX, skip on Windows)."""

from __future__ import annotations

import stat
import sys
from pathlib import Path

import pytest

from sysinstall.safety.audit import append_audit


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission model only")
class TestAuditLogPermissions:
    def test_audit_log_mode_is_0600(self, tmp_path: Path) -> None:
        """Audit log file must be readable/writable by owner only (mode 0o600)."""
        append_audit(
            action="test_action",
            target="disk:test:001",
            outcome="started",
            state_dir=tmp_path,
        )
        log_file = tmp_path / "audit.jsonl"
        assert log_file.exists(), "Audit log file was not created"
        mode = log_file.stat().st_mode
        # Extract permission bits only (strip type bits)
        perm_bits = stat.S_IMODE(mode)
        assert perm_bits == 0o600, (
            f"Expected audit log mode 0o600, got {oct(perm_bits)}. "
            "Audit logs must be owner-read/write only to protect sensitive data."
        )

    def test_audit_log_mode_persists_on_second_write(self, tmp_path: Path) -> None:
        """Mode 0o600 must be maintained after multiple appends."""
        for i in range(3):
            append_audit(
                action=f"test_action_{i}",
                target="disk:test:002",
                outcome="success",
                state_dir=tmp_path,
            )
        log_file = tmp_path / "audit.jsonl"
        perm_bits = stat.S_IMODE(log_file.stat().st_mode)
        assert perm_bits == 0o600

    def test_audit_log_not_world_readable(self, tmp_path: Path) -> None:
        """Verify others have no read/write/execute permission."""
        append_audit(
            action="test_action",
            target="disk:test:003",
            outcome="dry_run",
            state_dir=tmp_path,
        )
        log_file = tmp_path / "audit.jsonl"
        mode = log_file.stat().st_mode
        # Others bits must all be zero
        others_bits = mode & (stat.S_IROTH | stat.S_IWOTH | stat.S_IXOTH)
        assert others_bits == 0, (
            f"Audit log must not be accessible by others, got mode {oct(stat.S_IMODE(mode))}"
        )

    def test_audit_log_not_group_readable(self, tmp_path: Path) -> None:
        """Verify group has no read/write/execute permission."""
        append_audit(
            action="test_action",
            target="disk:test:004",
            outcome="success",
            state_dir=tmp_path,
        )
        log_file = tmp_path / "audit.jsonl"
        mode = log_file.stat().st_mode
        group_bits = mode & (stat.S_IRGRP | stat.S_IWGRP | stat.S_IXGRP)
        assert group_bits == 0, (
            f"Audit log must not be accessible by group, got mode {oct(stat.S_IMODE(mode))}"
        )
