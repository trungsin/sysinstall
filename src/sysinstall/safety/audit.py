"""JSONL audit log with size-based rotation.

Log location:
  Linux/macOS: $XDG_STATE_HOME/sysinstall/audit.jsonl
               (default: ~/.local/state/sysinstall/audit.jsonl)
  Windows:     %LOCALAPPDATA%\\sysinstall\\audit.jsonl

Rotation: when the active file exceeds *max_bytes* (default 100 MiB),
it is renamed to audit.jsonl.1, shifting older files up to .5, then
the oldest (.5) is deleted. Keeps at most *keep* rotated files.

Each entry is one JSON object per line:
  {"ts": "<iso8601>", "actor": "<user>", "action": "<str>",
   "target": "<disk_id>", "args": {}, "outcome": "started|success|failure|dry_run",
   "error": "<str>|null"}
"""

from __future__ import annotations

import getpass
import json
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Default rotation thresholds — can be overridden for testing via parameters.
_DEFAULT_MAX_BYTES = 100 * 1024 * 1024  # 100 MiB
_DEFAULT_KEEP = 5


def _state_dir() -> Path:
    """Return the platform-specific state directory, creating it if needed."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(
            os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")
        )
    state = base / "sysinstall"
    state.mkdir(parents=True, exist_ok=True)
    return state


def _audit_path(state_dir: Path | None = None) -> Path:
    """Return path to the active audit.jsonl file."""
    return (state_dir or _state_dir()) / "audit.jsonl"


def _rotate(log_path: Path, *, max_bytes: int, keep: int) -> None:
    """Rotate *log_path* if it exceeds *max_bytes*, keeping at most *keep* backups."""
    if not log_path.exists() or log_path.stat().st_size < max_bytes:
        return

    log.debug("Rotating audit log %s (size=%d)", log_path, log_path.stat().st_size)

    # Delete the oldest backup if it exists.
    oldest = log_path.parent / f"{log_path.name}.{keep}"
    if oldest.exists():
        oldest.unlink()

    # Shift existing backups: .4 -> .5, .3 -> .4, …, .1 -> .2
    for i in range(keep - 1, 0, -1):
        src = log_path.parent / f"{log_path.name}.{i}"
        dst = log_path.parent / f"{log_path.name}.{i + 1}"
        if src.exists():
            src.rename(dst)

    # Rename active log to .1
    log_path.rename(log_path.parent / f"{log_path.name}.1")


def append_audit(
    action: str,
    target: str,
    outcome: str,
    *,
    args: dict[str, Any] | None = None,
    error: str | None = None,
    state_dir: Path | None = None,
    max_bytes: int = _DEFAULT_MAX_BYTES,
    keep: int = _DEFAULT_KEEP,
) -> None:
    """Append one audit entry to the JSONL log.

    Args:
        action: Short action name, e.g. "usb_create".
        target: Disk ID or path being operated on.
        outcome: One of "started", "success", "failure", "dry_run".
        args: Additional key/value context (flags, options used).
        error: Error message string if outcome is "failure".
        state_dir: Override state directory (for tests).
        max_bytes: Rotate when log exceeds this size (injectable for tests).
        keep: Number of rotated files to retain (injectable for tests).
    """
    log_path = _audit_path(state_dir)

    _rotate(log_path, max_bytes=max_bytes, keep=keep)

    try:
        actor = getpass.getuser()
    except Exception:  # noqa: BLE001
        actor = "unknown"

    entry: dict[str, Any] = {
        "ts": datetime.now(tz=UTC).isoformat(),
        "actor": actor,
        "action": action,
        "target": target,
        "args": args or {},
        "outcome": outcome,
        "error": error,
    }

    try:
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        # Restrict to owner read/write on POSIX (0600).
        # Done after every write so newly created files are secured immediately.
        if sys.platform != "win32":
            log_path.chmod(0o600)
    except OSError as exc:
        # Audit failure must never crash the main operation.
        log.warning("Could not write audit log to %s: %s", log_path, exc)
