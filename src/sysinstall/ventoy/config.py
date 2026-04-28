"""ventoy.json read/write helpers.

The file lives at <usb_mount>/ventoy/ventoy.json on the first Ventoy partition.

Design contract:
- Unknown top-level keys from the user's existing ventoy.json are NEVER clobbered.
- sysinstall metadata lives exclusively under the "_sysinstall" namespace key.
- Stdlib json only — no pydantic, no third-party deps.
- read-modify-write cycles are protected by a file lock (fcntl on POSIX,
  msvcrt on Windows) via the ``locked_rw`` context manager.
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# The namespace key sysinstall writes into ventoy.json.
_NS = "_sysinstall"


@dataclass
class ManagedIso:
    """Metadata for an ISO tracked by sysinstall."""

    filename: str
    label: str
    added_ts: str  # ISO-8601


@dataclass
class VentoyConfig:
    """In-memory representation of ventoy.json.

    Attributes:
        managed_isos: ISOs tracked by sysinstall (stored under _sysinstall key).
            Used by the legacy Phase-03 API.  Mutations here are synced into
            _raw by write().
        _raw: The full parsed dict including all user/Ventoy-native keys.
            This is the source of truth for round-trip preservation.
            The iso.catalog module writes directly into _raw[_NS]["managed_isos"].
        _catalog_dirty: Internal flag set by iso.catalog helpers to indicate
            that _raw[_NS]["managed_isos"] has been updated by the catalog
            module rather than through cfg.managed_isos.
    """

    managed_isos: list[ManagedIso] = field(default_factory=list)
    _raw: dict[str, Any] = field(default_factory=dict, repr=False)
    _catalog_dirty: bool = field(default=False, repr=False, compare=False)


def _ventoy_json_path(usb_mount: Path) -> Path:
    return usb_mount / "ventoy" / "ventoy.json"


def make_skeleton() -> VentoyConfig:
    """Return the initial VentoyConfig written after a fresh Ventoy install."""
    raw: dict[str, Any] = {
        _NS: {
            "managed_by": "sysinstall",
            "managed_isos": [],
        }
    }
    return VentoyConfig(managed_isos=[], _raw=raw)


def read(usb_mount: Path) -> VentoyConfig:
    """Parse ventoy.json from *usb_mount*, preserving all existing keys.

    Args:
        usb_mount: Mount point of the Ventoy first partition (e.g. /mnt/ventoy).

    Returns:
        VentoyConfig with managed_isos populated from _sysinstall namespace.

    Raises:
        FileNotFoundError: ventoy.json does not exist.
        json.JSONDecodeError: file is malformed.
    """
    cfg_path = _ventoy_json_path(usb_mount)
    log.debug("Reading ventoy.json from %s", cfg_path)
    raw: dict[str, Any] = json.loads(cfg_path.read_text(encoding="utf-8"))

    ns: dict[str, Any] = raw.get(_NS, {})
    raw_isos: list[dict[str, Any]] = ns.get("managed_isos", [])
    managed = [
        ManagedIso(
            filename=iso["filename"],
            label=iso.get("label", ""),
            added_ts=iso.get("added_ts", ""),
        )
        for iso in raw_isos
    ]
    return VentoyConfig(managed_isos=managed, _raw=raw)


def write(usb_mount: Path, cfg: VentoyConfig) -> None:
    """Serialise *cfg* to ventoy.json, preserving all user-set top-level keys.

    Only the _sysinstall namespace is overwritten; every other key in
    cfg._raw is left untouched.

    Args:
        usb_mount: Mount point of the Ventoy first partition.
        cfg: Config to persist.
    """
    cfg_path = _ventoy_json_path(usb_mount)
    cfg_path.parent.mkdir(parents=True, exist_ok=True)

    # Merge: start from the preserved raw dict, update only our namespace.
    merged = dict(cfg._raw)  # shallow copy preserves unknown keys
    ns_dict: dict[str, Any] = dict(merged.get(_NS, {}))

    if cfg._catalog_dirty:
        # iso.catalog helpers wrote directly into cfg._raw[_NS]["managed_isos"].
        # Use _raw as the authoritative source — it already contains the
        # richer Phase-04 schema (sha256, size_bytes, name, added_at).
        # ns_dict already holds those values from the dict() copy above.
        pass
    else:
        # Legacy path: serialise from cfg.managed_isos (Phase-03 schema).
        ns_dict["managed_isos"] = [
            {
                "filename": iso.filename,
                "label": iso.label,
                "added_ts": iso.added_ts,
            }
            for iso in cfg.managed_isos
        ]

    ns_dict.setdefault("managed_by", "sysinstall")
    merged[_NS] = ns_dict

    log.debug("Writing ventoy.json to %s", cfg_path)
    cfg_path.write_text(
        json.dumps(merged, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# File-locked read-modify-write context manager
# ---------------------------------------------------------------------------

@contextmanager
def locked_rw(usb_mount: Path) -> Generator[VentoyConfig, None, None]:
    """Context manager that holds an exclusive file lock on ventoy.json.

    Reads the config on entry, yields it for mutation, then writes it back
    on exit.  The lock is released after the write completes.

    Uses ``fcntl.flock`` on POSIX, ``msvcrt.locking`` on Windows.

    Example::

        with ventoy_config.locked_rw(mount) as cfg:
            add_to_catalog(cfg, iso)
        # ventoy.json written & lock released here

    Args:
        usb_mount: Mount point of the Ventoy first partition.

    Yields:
        :class:`VentoyConfig` loaded from ventoy.json.

    Raises:
        FileNotFoundError: ventoy.json does not exist.
        OSError: lock or write failure.
    """
    cfg_path = _ventoy_json_path(usb_mount)
    cfg_path.parent.mkdir(parents=True, exist_ok=True)

    # Open (or create) the lock target; we lock the file itself.
    lock_fh = cfg_path.open("a+", encoding="utf-8")
    try:
        _acquire_lock(lock_fh)
        try:
            cfg = read(usb_mount)
            yield cfg
            write(usb_mount, cfg)
        finally:
            _release_lock(lock_fh)
    finally:
        lock_fh.close()


def _acquire_lock(fh: Any) -> None:
    """Acquire an exclusive lock on the open file handle *fh*."""
    if sys.platform == "win32":
        import msvcrt
        # Lock the first byte of the file (msvcrt.locking requires a size).
        try:
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)  # type: ignore[attr-defined,unused-ignore]
        except OSError:
            # Blocking lock — retry with LK_LOCK.
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)  # type: ignore[attr-defined,unused-ignore]
    else:
        import fcntl
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)


def _release_lock(fh: Any) -> None:
    """Release the lock on the open file handle *fh*."""
    if sys.platform == "win32":
        import msvcrt
        try:
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)  # type: ignore[attr-defined,unused-ignore]
        except OSError:
            pass
    else:
        import fcntl
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
