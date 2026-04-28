"""Boot subcommand group: detect, repair, revert.

All commands gate on Linux host (exit 2 on macOS/Windows).
repair also requires root (exit 2 if not sudo).
"""

from __future__ import annotations

import contextlib
import json
import sys
from pathlib import Path

import typer

from sysinstall.boot.types import RepairPlan, UnsupportedHostError

app = typer.Typer(help="Bootloader detection and repair commands.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _host_gate() -> None:
    """Exit 2 with a helpful message if not on Linux."""
    if sys.platform != "linux":
        typer.echo(
            "ERROR: Boot commands require a Linux environment.\n"
            "Boot from an Ubuntu live USB and re-run this command there.",
            err=True,
        )
        raise typer.Exit(2)


def _echo_progress(msg: str) -> None:
    typer.echo(msg)


# ---------------------------------------------------------------------------
# boot detect
# ---------------------------------------------------------------------------


@app.command("detect")
def detect_cmd(
    as_json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Detect current firmware mode and candidate boot partitions."""
    _host_gate()

    from sysinstall.boot import detect
    from sysinstall.safety.audit import append_audit

    append_audit("boot.detect", target="system", outcome="started")

    try:
        env = detect()
    except Exception as exc:
        typer.echo(f"ERROR: Detection failed: {exc}", err=True)
        append_audit("boot.detect", target="system", outcome="failure", error=str(exc))
        raise typer.Exit(1) from exc

    append_audit("boot.detect", target="system", outcome="success")

    if as_json:
        data = {
            "firmware": env.firmware,
            "candidate_efi": [p.id for p in env.candidate_efi],
            "candidate_linux_roots": [p.id for p in env.candidate_linux_roots],
            "candidate_windows": [p.id for p in env.candidate_windows],
            "boot_order": list(env.boot_order),
            "efi_entries": [
                {"num": e.num, "label": e.label, "active": e.active}
                for e in env.efi_entries
            ],
        }
        typer.echo(json.dumps(data, indent=2))
        return

    typer.echo(f"Firmware mode : {env.firmware.upper()}")
    typer.echo(f"EFI candidates: {[p.id for p in env.candidate_efi] or 'none'}")
    typer.echo(f"Linux roots   : {[p.id for p in env.candidate_linux_roots] or 'none'}")
    typer.echo(f"Windows parts : {[p.id for p in env.candidate_windows] or 'none'}")
    if env.boot_order:
        typer.echo(f"Boot order    : {', '.join(env.boot_order)}")
    if env.efi_entries:
        typer.echo("EFI entries:")
        for e in env.efi_entries:
            active_flag = "*" if e.active else " "
            typer.echo(f"  Boot{e.num}{active_flag} {e.label}")


# ---------------------------------------------------------------------------
# boot repair
# ---------------------------------------------------------------------------


@app.command("repair")
def repair_cmd(
    ctx: typer.Context,
    ubuntu_root: str = typer.Option(
        ...,
        "--ubuntu-root",
        help="Partition ID or device path for the Ubuntu root (e.g. /dev/sda3).",
    ),
    efi: str | None = typer.Option(
        None,
        "--efi",
        help="Partition ID or device path for the ESP (required for UEFI).",
    ),
    no_os_prober: bool = typer.Option(
        False,
        "--no-os-prober",
        help="Skip enabling GRUB_DISABLE_OS_PROBER=false.",
    ),
    no_set_boot_order: bool = typer.Option(
        False,
        "--no-set-boot-order",
        help="Skip adjusting EFI boot order.",
    ),
    use_boot_repair: bool = typer.Option(
        False,
        "--use-boot-repair",
        help="Delegate to boot-repair CLI instead of manual chroot path.",
    ),
    confirm: bool = typer.Option(
        False,
        "--confirm",
        help="Skip interactive confirmation prompt.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Log all steps but do not execute destructive operations.",
    ),
    as_json: bool = typer.Option(False, "--json", help="Emit machine-readable output."),
    no_banner: bool = typer.Option(
        False,
        "--no-banner",
        hidden=True,
        help="Skip countdown banner (CI/automation only).",
    ),
) -> None:
    """Repair GRUB bootloader on an Ubuntu + Windows dual-boot system.

    Requires root (run with sudo) and a Linux host (Ubuntu live USB session).
    """
    _host_gate()

    from sysinstall.boot.detector import is_uefi
    from sysinstall.boot.types import RepairPlan
    from sysinstall.cli import merge_global_flags
    from sysinstall.disks import list_disks
    from sysinstall.safety import SafetyError, check_destructive
    from sysinstall.safety.prompts import confirm_with_banner

    flags = merge_global_flags(ctx, confirm=confirm, dry_run=dry_run)

    # Resolve partitions from disk list.
    disks = list_disks()
    all_parts = {p.id: p for d in disks for p in d.partitions}
    # Also allow matching by device path if the id IS the path.
    all_parts.update({p.id: p for p in all_parts.values()})

    root_part = all_parts.get(ubuntu_root)
    if root_part is None:
        typer.echo(
            f"ERROR: Partition '{ubuntu_root}' not found. "
            "Run 'sysinstall boot detect' to list available partitions.",
            err=True,
        )
        raise typer.Exit(2)

    firmware = "uefi" if is_uefi() else "bios"

    efi_part = None
    if efi is not None:
        efi_part = all_parts.get(efi)
        if efi_part is None:
            typer.echo(f"ERROR: EFI partition '{efi}' not found.", err=True)
            raise typer.Exit(2)
    elif firmware == "uefi":
        typer.echo(
            "ERROR: --efi <partition> is required in UEFI mode.", err=True
        )
        raise typer.Exit(2)

    # Safety gate on the disk containing the root partition.
    # Find parent disk of root_part.
    root_disk = next(
        (d for d in disks if any(p.id == root_part.id for p in d.partitions)),
        None,
    )
    if root_disk is not None:
        try:
            check_destructive(
                root_disk,
                "boot_repair",
                allow_fixed=flags.get("allow_fixed_disk", True),
                force_encrypted=flags.get("force_encrypted", False),
                auto_unmount=flags.get("auto_unmount", False),
            )
        except SafetyError as exc:
            typer.echo(f"ERROR: {exc}", err=True)
            if exc.suggestion:
                typer.echo(f"Hint: {exc.suggestion}", err=True)
            raise typer.Exit(2) from exc

    plan = RepairPlan(
        firmware=firmware,  # type: ignore[arg-type]
        efi_partition=efi_part,
        root_partition=root_part,
        enable_os_prober=not no_os_prober,
        set_boot_order_first=not no_set_boot_order,
    )

    # Pre-confirm summary.
    _show_repair_prompt(plan, dry_run=flags["dry_run"])

    # Red-banner confirm with countdown.
    if root_disk is not None:
        confirm_with_banner(
            root_disk,
            "boot_repair",
            "repair GRUB bootloader (chroot + grub-install + update-grub)",
            confirmed=flags["confirm"],
            no_banner=no_banner,
        )
    elif not flags["confirm"] and not flags["dry_run"]:
        typer.echo("")
        response = typer.prompt(
            "Type 'yes' to proceed with boot repair",
            default="no",
        )
        if response.strip().lower() != "yes":
            typer.echo("Aborted.")
            raise typer.Abort()

    from sysinstall.boot import repair

    try:
        repair(
            plan,
            dry_run=flags["dry_run"],
            use_boot_repair=use_boot_repair,
            on_progress=_echo_progress,
        )
    except UnsupportedHostError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(2) from exc
    except SystemExit:
        raise
    except Exception as exc:
        typer.echo(f"ERROR: Repair failed: {exc}", err=True)
        raise typer.Exit(1) from exc

    if as_json:
        typer.echo(json.dumps({"status": "success", "dry_run": flags["dry_run"]}))
    else:
        mode = " [dry-run]" if flags["dry_run"] else ""
        typer.echo(f"Boot repair completed successfully{mode}.")


def _show_repair_prompt(plan: RepairPlan, *, dry_run: bool) -> None:
    """Display a detailed pre-confirm summary of planned actions."""
    typer.echo("")
    typer.echo("=" * 60)
    typer.echo("  BOOT REPAIR PLAN")
    typer.echo("=" * 60)
    typer.echo(f"  Firmware mode  : {plan.firmware.upper()}")
    typer.echo(f"  Ubuntu root    : {plan.root_partition.id}"
               f"  ({plan.root_partition.label or 'no label'}"
               f", {plan.root_partition.size_bytes // (1024**3)} GiB)")
    if plan.efi_partition:
        typer.echo(f"  ESP partition  : {plan.efi_partition.id}"
                   f"  ({plan.efi_partition.label or 'no label'}"
                   f", {plan.efi_partition.size_bytes // (1024**2)} MiB)")
    typer.echo(f"  Enable os-prober : {'yes' if plan.enable_os_prober else 'no'}")
    typer.echo(f"  Set boot order   : {'yes' if plan.set_boot_order_first else 'no'}")
    if dry_run:
        typer.echo("  Mode           : DRY RUN (no changes will be made)")
    typer.echo("")
    typer.echo("  Planned actions:")
    typer.echo("    1. Mount root partition + ESP + bind-mounts")
    if plan.enable_os_prober:
        typer.echo("    2. Set GRUB_DISABLE_OS_PROBER=false")
    typer.echo("    3. Run grub-install inside chroot")
    typer.echo("    4. Run update-grub inside chroot")
    if plan.firmware == "uefi" and plan.set_boot_order_first:
        typer.echo("    5. Set EFI boot order: Ubuntu first")
    typer.echo("")
    typer.echo(
        "  WARNING: Windows next boot may demand BitLocker recovery key"
        " — have it ready."
    )
    typer.echo("  IMPORTANT: Back up your data before proceeding.", )
    typer.echo("=" * 60)


# ---------------------------------------------------------------------------
# boot revert
# ---------------------------------------------------------------------------


@app.command("revert")
def revert_cmd(
    backup_file: Path | None = typer.Option(  # noqa: B008
        None,
        "--backup-file",
        help="Path to ESP backup tar. Defaults to the latest snapshot.",
    ),
    efi: str = typer.Option(
        ...,
        "--efi",
        help="Partition ID or device path for the ESP to restore into.",
    ),
    confirm: bool = typer.Option(
        False,
        "--confirm",
        help="Skip interactive confirmation.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Log intent but do not restore.",
    ),
) -> None:
    """Restore the ESP from the latest (or specified) snapshot.

    Requires root and a Linux host.
    """
    _host_gate()

    from sysinstall.boot.backup import latest_snapshot, restore_esp
    from sysinstall.disks import list_disks
    from sysinstall.safety.audit import append_audit

    disks = list_disks()
    all_parts = {p.id: p for d in disks for p in d.partitions}
    efi_part = all_parts.get(efi)
    if efi_part is None:
        typer.echo(f"ERROR: EFI partition '{efi}' not found.", err=True)
        raise typer.Exit(2)

    # Resolve backup path.
    resolved_backup: Path | None = backup_file
    if resolved_backup is None:
        resolved_backup = latest_snapshot()
        if resolved_backup is None:
            typer.echo("ERROR: No ESP snapshots found. Run 'boot repair' first.", err=True)
            raise typer.Exit(2)

    typer.echo(f"Restoring ESP from: {resolved_backup}")
    typer.echo(f"Target ESP        : {efi_part.id}")

    if not confirm and not dry_run:
        response = typer.prompt("Type 'yes' to restore", default="no")
        if response.strip().lower() != "yes":
            typer.echo("Aborted.")
            raise typer.Abort()

    append_audit(
        "boot.revert.start",
        target=efi_part.id,
        outcome="dry_run" if dry_run else "started",
        args={"backup": str(resolved_backup)},
    )

    # For restore we need the ESP mounted. In a live session it may already
    # be mounted; we attempt to mount it if not, then restore.
    import tempfile
    tmpdir = tempfile.mkdtemp(prefix="sysinstall-esp-restore-")
    mounted = False
    try:
        if sys.platform == "linux" and not dry_run:
            import subprocess
            result = subprocess.run(
                ["mount", efi_part.id, tmpdir],
                capture_output=True,
                timeout=30,
            )
            if result.returncode != 0:
                typer.echo(
                    f"ERROR: Could not mount ESP {efi_part.id}: "
                    f"{result.stderr.decode().strip()}",
                    err=True,
                )
                raise typer.Exit(1)
            mounted = True

        restore_esp(resolved_backup, Path(tmpdir), dry_run=dry_run)
    finally:
        if mounted:
            import subprocess
            subprocess.run(["umount", tmpdir], capture_output=True, timeout=30)
        with contextlib.suppress(OSError):
            Path(tmpdir).rmdir()

    typer.echo("ESP restore completed successfully.")
