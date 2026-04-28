"""ESP snapshot and restore for boot revert operations.

Snapshots are stored as tar archives in ~/.local/state/sysinstall/.
Format: esp-backup-<iso8601-ts>.tar

snapshot_esp: tar the ESP mountpoint into the state dir.
restore_esp:  untar a backup back onto the ESP mountpoint.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from sysinstall.safety.audit import append_audit

log = logging.getLogger(__name__)

_TAR_TIMEOUT = 120


def _state_dir() -> Path:
    """Return ~/.local/state/sysinstall, creating it if needed."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(
            os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")
        )
    state = base / "sysinstall"
    state.mkdir(parents=True, exist_ok=True)
    return state


def snapshot_esp(
    efi_part_mountpoint: Path,
    *,
    state_dir: Path | None = None,
    dry_run: bool = False,
) -> Path:
    """Create a tar archive of the ESP contents.

    Args:
        efi_part_mountpoint: Mounted path of the ESP (e.g. /boot/efi or a tmpdir).
        state_dir: Override state dir for testing.
        dry_run: Log intent but do not create archive.

    Returns:
        Path to the created archive (or would-be path in dry-run).

    Raises:
        RuntimeError: if tar fails.
    """
    ts = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    dest_dir = state_dir or _state_dir()
    backup_path = dest_dir / f"esp-backup-{ts}.tar"

    append_audit(
        "boot.revert.snapshot",
        target=str(efi_part_mountpoint),
        outcome="dry_run" if dry_run else "started",
        args={"backup_path": str(backup_path)},
    )

    if dry_run:
        log.info("[dry-run] would snapshot ESP %s -> %s", efi_part_mountpoint, backup_path)
        return backup_path

    args = [
        "tar",
        "--create",
        "--file", str(backup_path),
        "--directory", str(efi_part_mountpoint),
        ".",
    ]
    result = subprocess.run(args, capture_output=True, timeout=_TAR_TIMEOUT)
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace").strip()
        append_audit(
            "boot.revert.snapshot",
            target=str(efi_part_mountpoint),
            outcome="failure",
            error=stderr,
        )
        raise RuntimeError(f"tar snapshot failed: {stderr}")

    append_audit(
        "boot.revert.snapshot",
        target=str(efi_part_mountpoint),
        outcome="success",
        args={"backup_path": str(backup_path)},
    )
    log.info("ESP snapshot saved to %s", backup_path)
    return backup_path


def restore_esp(
    backup_path: Path,
    efi_part_mountpoint: Path,
    *,
    dry_run: bool = False,
) -> None:
    """Restore an ESP snapshot onto a mounted ESP.

    Args:
        backup_path: Path to the tar archive created by snapshot_esp.
        efi_part_mountpoint: Mounted path of the ESP to restore into.
        dry_run: Log intent but do not extract.

    Raises:
        FileNotFoundError: if backup_path does not exist.
        RuntimeError: if tar fails.
    """
    if not backup_path.exists():
        raise FileNotFoundError(f"ESP backup not found: {backup_path}")

    append_audit(
        "boot.revert.restore",
        target=str(efi_part_mountpoint),
        outcome="dry_run" if dry_run else "started",
        args={"backup_path": str(backup_path)},
    )

    if dry_run:
        log.info("[dry-run] would restore %s -> %s", backup_path, efi_part_mountpoint)
        return

    args = [
        "tar",
        "--extract",
        "--overwrite",
        "--file", str(backup_path),
        "--directory", str(efi_part_mountpoint),
    ]
    result = subprocess.run(args, capture_output=True, timeout=_TAR_TIMEOUT)
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace").strip()
        append_audit(
            "boot.revert.restore",
            target=str(efi_part_mountpoint),
            outcome="failure",
            error=stderr,
        )
        raise RuntimeError(f"tar restore failed: {stderr}")

    append_audit(
        "boot.revert.restore",
        target=str(efi_part_mountpoint),
        outcome="success",
    )
    log.info("ESP restored from %s to %s", backup_path, efi_part_mountpoint)


def latest_snapshot(state_dir: Path | None = None) -> Path | None:
    """Return the most recent ESP backup path, or None if no backups exist."""
    dest_dir = state_dir or _state_dir()
    candidates = sorted(dest_dir.glob("esp-backup-*.tar"), reverse=True)
    return candidates[0] if candidates else None
