"""Stable disk ID derivation.

A stable ID must survive reboots and device re-enumeration. We derive it from
content-based attributes (bus, serial, model, size) rather than ephemeral
device paths like /dev/sdX or drive letters.

Format:
  - With serial:   "<bus>:<serial_hex8>"
  - Without serial: "unstable:<blake2b8_of_model_size_order>"
    The "unstable:" prefix signals that the ID may change if device order changes.
"""

from __future__ import annotations

import hashlib


def make_stable_id(
    bus: str,
    serial: str | None,
    model: str,
    size_bytes: int,
    order: int = 0,
) -> str:
    """Return a short stable disk identifier.

    Args:
        bus: Normalised bus type string (usb, sata, nvme, scsi, unknown).
        serial: Manufacturer serial number, or None if unavailable.
        model: Disk model string (used as fallback when serial absent).
        size_bytes: Total disk size in bytes.
        order: Zero-based enumeration index; only used in the fallback path.

    Returns:
        A string suitable for use as a disk ID, e.g. "nvme:a1b2c3d4e5f6a7b8"
        or "unstable:c0ffee12" if no serial is available.
    """
    bus_norm = bus.lower().strip()

    if serial:
        serial_clean = serial.strip()
        if serial_clean:
            # Hash bus+serial for a compact, filesystem-safe token.
            digest = _short_hash(f"{bus_norm}:{serial_clean}")
            return f"{bus_norm}:{digest}"

    # Fallback: derive from model + size + order (order-dependent = unstable).
    digest = _short_hash(f"{model.strip()}:{size_bytes}:{order}")
    return f"unstable:{digest}"


def _short_hash(text: str) -> str:
    """Return 16 hex characters (8 bytes) of blake2b hash of *text*."""
    h = hashlib.blake2b(text.encode(), digest_size=8)
    return h.hexdigest()
