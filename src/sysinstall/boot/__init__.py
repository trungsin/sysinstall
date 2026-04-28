"""Public API for the boot module.

Linux-host gate is enforced at the top of repair() before any disk access.

Usage::

    from sysinstall.boot import detect, repair
    from sysinstall.boot.types import RepairPlan

    env = detect()
    plan = RepairPlan(
        firmware=env.firmware,
        efi_partition=env.candidate_efi[0],
        root_partition=env.candidate_linux_roots[0],
        enable_os_prober=True,
        set_boot_order_first=True,
    )
    repair(plan, dry_run=True)
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable

from sysinstall.boot.types import (
    BootEnvironment,
    EfiEntry,
    FirmwareMode,
    RepairPlan,
    UnsupportedHostError,
)
from sysinstall.disks.base import Disk

__all__ = [
    "detect",
    "repair",
    "BootEnvironment",
    "EfiEntry",
    "FirmwareMode",
    "RepairPlan",
    "UnsupportedHostError",
]


def _assert_linux_host() -> None:
    """Raise UnsupportedHostError if not running on Linux.

    This gate runs BEFORE any partition resolution or subprocess calls.
    """
    if sys.platform != "linux":
        raise UnsupportedHostError(
            "Boot repair requires a Linux environment.\n"
            "Boot from an Ubuntu live USB and re-run this command there."
        )


def _assert_root() -> None:
    """Raise SystemExit(2) if not running as root."""
    if os.geteuid() != 0:  # type: ignore[attr-defined,unused-ignore]
        import typer
        typer.echo(
            "ERROR: boot repair requires root privileges. Run with sudo.",
            err=True,
        )
        raise SystemExit(2)


def detect(disks: list[Disk] | None = None) -> BootEnvironment:
    """Detect the current boot environment.

    Identifies firmware mode (UEFI/BIOS) and classifies partitions
    into ESP, Linux root, and Windows candidates.

    Unlike repair(), detect() is allowed to run on any host — it returns
    a BootEnvironment with empty candidate lists on non-Linux hosts.

    Args:
        disks: Optional pre-loaded disk list (for testing).

    Returns:
        BootEnvironment describing the detected configuration.
    """
    from sysinstall.boot.detector import find_candidates
    return find_candidates(disks=disks)


def repair(
    plan: RepairPlan,
    *,
    dry_run: bool = False,
    use_boot_repair: bool = False,
    on_progress: Callable[[str], None] | None = None,
) -> None:
    """Execute a boot repair according to the given plan.

    Linux-host gate is enforced here before any disk or subprocess access.
    Root check is also enforced (exit 2 if not root).

    Args:
        plan: RepairPlan describing partitions and options.
        dry_run: Log all actions but skip destructive subprocess calls.
        use_boot_repair: If True, delegate to the boot-repair CLI tool
                         instead of the manual chroot path. Exits 2 if
                         boot-repair is not installed.
        on_progress: Optional callback receiving human-readable progress strings.

    Raises:
        UnsupportedHostError: if not running on Linux.
        SystemExit(2): if not running as root, or boot-repair missing with
                       --use-boot-repair.
        RuntimeError: if any repair step fails.
    """
    # Gate 1: Linux host required.
    _assert_linux_host()

    # Gate 2: Root required (don't auto-elevate).
    if not dry_run:
        _assert_root()

    from sysinstall.safety.audit import append_audit

    append_audit(
        "boot.repair.start",
        target=plan.root_partition.id,
        outcome="dry_run" if dry_run else "started",
        args={
            "use_boot_repair": use_boot_repair,
            "firmware": plan.firmware,
            "enable_os_prober": plan.enable_os_prober,
        },
    )

    if use_boot_repair:
        from sysinstall.boot.orchestrator import run_boot_repair_tool
        try:
            run_boot_repair_tool(dry_run=dry_run, on_progress=on_progress)
        except FileNotFoundError as exc:
            import typer
            typer.echo(f"ERROR: {exc}", err=True)
            raise SystemExit(2) from exc
        return

    from sysinstall.boot.orchestrator import run_manual_repair
    run_manual_repair(plan, dry_run=dry_run, on_progress=on_progress)
