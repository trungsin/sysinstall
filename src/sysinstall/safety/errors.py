"""Typed exception for safety gate refusals.

SafetyError carries structured metadata so callers can distinguish
refusal categories and present targeted remediation hints.
"""

from __future__ import annotations

from typing import Literal

# Gate category labels — used to route error handling in CLI layers.
SafetyCategory = Literal[
    "system_disk",
    "encrypted",
    "fixed_disk",
    "mounted",
    "unknown_id",
]


class SafetyError(Exception):
    """Raised when a safety gate refuses an operation.

    Attributes:
        category: Machine-readable refusal category.
        overridable: True when the user can pass a flag to bypass.
        suggestion: Human-readable hint for how to proceed (or not).
        disk_id: Stable disk ID that triggered the refusal.
        op: Operation name that was being checked.
    """

    def __init__(
        self,
        message: str,
        *,
        category: SafetyCategory,
        overridable: bool,
        suggestion: str,
        disk_id: str = "",
        op: str = "",
    ) -> None:
        super().__init__(message)
        self.category: SafetyCategory = category
        self.overridable = overridable
        self.suggestion = suggestion
        self.disk_id = disk_id
        self.op = op

    def __repr__(self) -> str:
        return (
            f"SafetyError({str(self)!r}, category={self.category!r}, "
            f"overridable={self.overridable}, disk_id={self.disk_id!r})"
        )
