"""Catalog of sysinstall-managed ISOs stored inside ventoy.json.

All ISOs are persisted under cfg._raw["_sysinstall"]["managed_isos"].
Unknown Ventoy plugin keys (control, theme, auto_install, …) are never
touched — round-trip safety is enforced at the ventoy.config layer.

Filename validation regex:
    ^[A-Za-z0-9._\\- ]+\\.iso$   (case-insensitive .iso/.ISO extension)
Path traversal sequences (.., /, \\) are rejected before the regex runs.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from sysinstall.ventoy.config import VentoyConfig

# Filename allowlist — only safe characters, must end in .iso/.ISO.
_FILENAME_RE = re.compile(r"^[A-Za-z0-9._\- ]+\.iso$", re.IGNORECASE)

# Path traversal sequences that are rejected unconditionally.
_TRAVERSAL_PATTERNS = ("..", "/", "\\")

_NS = "_sysinstall"


@dataclass
class ManagedIso:
    """Metadata for a sysinstall-tracked ISO on the Ventoy USB."""

    filename: str    # actual filename on the USB root
    name: str        # user-facing alias / label
    sha256: str      # sha256 hex digest at add-time
    size_bytes: int
    added_at: str    # ISO-8601 timestamp


def validate_filename(filename: str) -> None:
    """Raise ValueError if *filename* is unsafe or does not match the allowlist.

    Args:
        filename: Bare filename (no directory component expected).

    Raises:
        ValueError: filename contains path traversal sequences or does not
            match ``^[A-Za-z0-9._\\- ]+\\.iso$``.
    """
    for seq in _TRAVERSAL_PATTERNS:
        if seq in filename:
            raise ValueError(
                f"Filename {filename!r} contains disallowed sequence {seq!r}. "
                "Path traversal is not permitted."
            )
    if not _FILENAME_RE.match(filename):
        raise ValueError(
            f"Filename {filename!r} does not match the allowed pattern "
            r"'^[A-Za-z0-9._\- ]+\.iso$' (case-insensitive)."
        )


def _get_catalog(cfg: VentoyConfig) -> list[dict[str, Any]]:
    """Return the mutable managed_isos list from cfg._raw.

    Sets ``cfg._catalog_dirty`` so that ``ventoy.config.write()`` knows to
    serialise from ``_raw`` rather than the legacy ``cfg.managed_isos`` list.
    """
    ns: dict[str, Any] = cfg._raw.setdefault(_NS, {})
    catalog: list[dict[str, Any]] = ns.setdefault("managed_isos", [])
    cfg._catalog_dirty = True  # signal write() to use _raw as source of truth
    return catalog


def add_to_catalog(cfg: VentoyConfig, iso: ManagedIso) -> None:
    """Append *iso* to the catalog inside *cfg*.

    Mutates ``cfg._raw`` in-place; call ``ventoy.config.write()`` to persist.

    Args:
        cfg: VentoyConfig loaded from the target USB.
        iso: ISO metadata to record.

    Raises:
        ValueError: iso.filename is invalid.
    """
    validate_filename(iso.filename)
    catalog = _get_catalog(cfg)
    catalog.append(asdict(iso))


def remove_from_catalog(cfg: VentoyConfig, identifier: str) -> ManagedIso:
    """Remove the ISO matching *identifier* (filename or name) from *cfg*.

    Mutates ``cfg._raw`` in-place; call ``ventoy.config.write()`` to persist.

    Args:
        cfg: VentoyConfig loaded from the target USB.
        identifier: Either the ISO's ``filename`` or ``name`` field.

    Returns:
        The removed :class:`ManagedIso`.

    Raises:
        KeyError: no ISO matches *identifier*.
    """
    catalog = _get_catalog(cfg)
    for i, entry in enumerate(catalog):
        if entry.get("filename") == identifier or entry.get("name") == identifier:
            removed = catalog.pop(i)
            return ManagedIso(
                filename=removed["filename"],
                name=removed["name"],
                sha256=removed["sha256"],
                size_bytes=removed["size_bytes"],
                added_at=removed["added_at"],
            )
    raise KeyError(f"No managed ISO matches identifier {identifier!r}.")


def find_in_catalog(cfg: VentoyConfig, identifier: str) -> ManagedIso | None:
    """Return the :class:`ManagedIso` matching *identifier*, or ``None``.

    Args:
        cfg: VentoyConfig to search.
        identifier: Either the ISO's ``filename`` or ``name`` field.
    """
    catalog = _get_catalog(cfg)
    for entry in catalog:
        if entry.get("filename") == identifier or entry.get("name") == identifier:
            return ManagedIso(
                filename=entry["filename"],
                name=entry["name"],
                sha256=entry["sha256"],
                size_bytes=entry["size_bytes"],
                added_at=entry["added_at"],
            )
    return None


def list_catalog(cfg: VentoyConfig) -> list[ManagedIso]:
    """Return all :class:`ManagedIso` entries from *cfg*.

    Args:
        cfg: VentoyConfig to read.
    """
    catalog = _get_catalog(cfg)
    return [
        ManagedIso(
            filename=entry["filename"],
            name=entry["name"],
            sha256=entry["sha256"],
            size_bytes=entry["size_bytes"],
            added_at=entry["added_at"],
        )
        for entry in catalog
    ]
