"""Typed exceptions for the ISO management module."""

from __future__ import annotations


class NotAVentoyUSBError(RuntimeError):
    """Raised when the target disk is not a Ventoy USB (no ventoy/ventoy.json)."""


class InsufficientSpaceError(RuntimeError):
    """Raised when the USB lacks enough free space to copy the ISO.

    Attributes:
        required: Bytes required (iso_size + 50 MiB headroom).
        available: Bytes actually free on the filesystem.
    """

    def __init__(self, required: int, available: int) -> None:
        self.required = required
        self.available = available
        super().__init__(
            f"Insufficient space: need {required:,} bytes "
            f"({required / 1024**2:.1f} MiB) but only "
            f"{available:,} bytes ({available / 1024**2:.1f} MiB) available."
        )
