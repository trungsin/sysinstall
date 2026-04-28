"""Public API for the partition module.

Usage:
    from sysinstall.partition import plan, apply
    from sysinstall.partition.layout import DualBootLayout
    from sysinstall.partition.planner import PartitionPlan

    layout = DualBootLayout(windows_size_gb=100, swap_size_gb=4,
                            disk_size_bytes=disk.size_bytes)
    partition_plan = plan(disk, layout)
    apply(partition_plan, dry_run=True)

Platform dispatch:
    darwin  -> runner_macos
    win32   -> runner_windows
    else    -> runner_linux
"""

from __future__ import annotations

import sys
from collections.abc import Callable

from sysinstall.disks.base import Disk
from sysinstall.partition.layout import DualBootLayout
from sysinstall.partition.planner import PartitionPlan
from sysinstall.partition.planner import plan as _compute_plan
from sysinstall.partition.preflight import EncryptionStatus, check_encryption, unmount_all
from sysinstall.safety.audit import append_audit
from sysinstall.safety.guards import refuse_if_system

__all__ = [
    "plan",
    "apply",
    "PartitionPlan",
    "DualBootLayout",
    "EncryptionStatus",
]


def plan(disk: Disk, layout: DualBootLayout) -> PartitionPlan:
    """Compute the dual-boot partition plan for *disk* given *layout*.

    This is a pure function — no subprocess calls, no side effects.

    Args:
        disk: Target disk.
        layout: Validated layout constraints.

    Returns:
        Fully resolved :class:`PartitionPlan`.

    Raises:
        LayoutTooLargeError: Plan does not fit on disk.
    """
    partition_plan = _compute_plan(disk, layout)
    append_audit(
        "partition.plan",
        disk.id,
        "success",
        args={
            "windows_size_gb": layout.windows_size_gb,
            "swap_size_gb": layout.swap_size_gb,
            "partitions": len(partition_plan.partitions),
            "total_required_mb": partition_plan.total_required_mb,
        },
    )
    return partition_plan


def apply(
    partition_plan: PartitionPlan,
    *,
    dry_run: bool = False,
    allow_encrypted: bool = False,
    on_progress: Callable[[str], None] | None = None,
) -> None:
    """Apply *partition_plan* to its target disk.

    Safety checks performed (in order):
      1. System-disk refusal (no override — hardcoded).
      2. Encryption check — refuse if encrypted unless allow_encrypted=True.
      3. Unmount all partitions (best-effort, warnings only).
      4. Dispatch to platform runner.

    Args:
        partition_plan: Plan produced by :func:`plan`.
        dry_run: Print commands without executing any subprocess.
        allow_encrypted: Skip the encryption refusal (clearly audited).
        on_progress: Optional callback receiving status strings.

    Raises:
        typer.Exit(2): System-disk detected.
        RuntimeError: Encryption refused, or a runner step failed.
    """
    disk = partition_plan.disk

    # --- 1. System-disk refusal (no escape hatch) ---
    refuse_if_system(disk)

    # --- 2. Encryption check ---
    enc_status = check_encryption(disk)
    if enc_status in (EncryptionStatus.partial, EncryptionStatus.full):
        if not allow_encrypted:
            append_audit(
                "partition.apply.refused",
                disk.id,
                "failure",
                args={"reason": "encrypted", "status": enc_status.value},
            )
            raise RuntimeError(
                f"Disk {disk.path} appears to be encrypted ({enc_status.value}). "
                "Wiping it will guarantee data loss. "
                "Pass --allow-encrypted to proceed (clearly logged in audit)."
            )
        # User explicitly allowed — log it prominently
        append_audit(
            "partition.apply.encryption_override",
            disk.id,
            "started",
            args={"status": enc_status.value, "allow_encrypted": True},
        )

    # --- 3. Unmount (best-effort) ---
    if not dry_run:
        warnings = unmount_all(disk)
        for w in warnings:
            if on_progress:
                on_progress(f"WARNING: {w}")

    # --- 4. Platform dispatch ---
    if sys.platform == "darwin":
        from sysinstall.partition.runner_macos import apply as _apply
    elif sys.platform == "win32":
        from sysinstall.partition.runner_windows import apply as _apply
    else:
        from sysinstall.partition.runner_linux import apply as _apply

    _apply(partition_plan, dry_run=dry_run, on_progress=on_progress)
