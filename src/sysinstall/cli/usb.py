"""USB subcommand group: create, update, info.

Commands:
  usb create   -- install Ventoy onto a target USB disk
  usb update   -- update an existing Ventoy installation
  usb info     -- show Ventoy status on a disk
"""

from __future__ import annotations

import logging
import sys

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

from sysinstall.disks.base import Disk
from sysinstall.safety.audit import append_audit

log = logging.getLogger(__name__)
console = Console()
err_console = Console(stderr=True)

app = typer.Typer(help="USB drive commands.")


def _resolve_disk(device: str) -> Disk:
    """Resolve disk by ID or path; exit 2 if not found."""
    from sysinstall.disks import get_disk, list_disks

    try:
        return get_disk(device)
    except KeyError:
        pass

    all_disks = list_disks()
    for d in all_disks:
        if d.path == device:
            return d

    err_console.print(
        f"[red]ERROR:[/red] No disk found matching {device!r}. "
        "Run 'sysinstall disk list' to see available disks."
    )
    raise typer.Exit(2)


@app.command("create")
def usb_create(
    ctx: typer.Context,
    device: str = typer.Option(
        ...,
        "--device",
        "-d",
        help="Disk ID or device path (e.g. usb:Kingston:... or /dev/sdb).",
    ),
    reserve_mb: int = typer.Option(
        0,
        "--reserve-mb",
        help="Reserve trailing space on USB in MB.",
    ),
    secure_boot: bool = typer.Option(
        False,
        "--secure-boot",
        help="Enable Ventoy Secure Boot support.",
    ),
    allow_fixed_disk: bool = typer.Option(
        False,
        "--allow-fixed-disk",
        help="Allow installation on non-removable disks (use with caution).",
    ),
    force_encrypted: bool = typer.Option(
        False,
        "--force-encrypted",
        help="Proceed on encrypted disks with a warning instead of refusing.",
    ),
    auto_unmount: bool = typer.Option(
        False,
        "--auto-unmount",
        help="Automatically unmount mounted partitions before writing.",
    ),
    confirm: bool = typer.Option(
        False,
        "--confirm",
        help="Skip the interactive confirmation prompt.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be done without making any changes.",
    ),
    no_banner: bool = typer.Option(
        False,
        "--no-banner",
        hidden=True,
        help="Skip countdown banner (CI/automation use only).",
    ),
) -> None:
    """Install Ventoy onto a USB disk, making it bootable with multiple ISOs."""
    from sysinstall.cli import merge_global_flags
    from sysinstall.safety import SafetyError, check_destructive
    from sysinstall.safety.prompts import confirm_with_banner
    from sysinstall.ventoy import UnsupportedHostError, install_to_disk

    # macOS hard-fail before touching anything.
    if sys.platform == "darwin":
        from sysinstall.ventoy import MACOS_VENTOY_MESSAGE
        err_console.print(f"[red]ERROR:[/red] {MACOS_VENTOY_MESSAGE}")
        raise typer.Exit(2)

    disk = _resolve_disk(device)

    # Merge per-subcommand flags with global context flags.
    flags = merge_global_flags(
        ctx,
        confirm=confirm,
        dry_run=dry_run,
        allow_fixed_disk=allow_fixed_disk,
        force_encrypted=force_encrypted,
        auto_unmount=auto_unmount,
    )

    # Unified safety gate pipeline — system disk is NEVER overridable.
    try:
        check_destructive(
            disk,
            "usb_create",
            allow_fixed=flags["allow_fixed_disk"],
            force_encrypted=flags["force_encrypted"],
            auto_unmount=flags["auto_unmount"],
        )
    except SafetyError as exc:
        err_console.print(f"[red]ERROR:[/red] {exc}")
        if exc.suggestion:
            err_console.print(f"[yellow]Hint:[/yellow] {exc.suggestion}")
        raise typer.Exit(2) from exc

    # Rich red-banner confirm with countdown.
    confirm_with_banner(
        disk,
        "usb_create",
        f"install Ventoy (secure_boot={secure_boot}, reserve_mb={reserve_mb})",
        confirmed=flags["confirm"],
        no_banner=no_banner,
    )

    audit_args = {
        "secure_boot": secure_boot,
        "reserve_mb": reserve_mb,
        "allow_fixed_disk": flags["allow_fixed_disk"],
        "dry_run": flags["dry_run"],
    }
    append_audit("usb_create", disk.id, "started", args=audit_args)

    if flags["dry_run"]:
        console.print(
            f"[yellow][dry-run][/yellow] Would install Ventoy on {disk.path} "
            f"(model={disk.model!r}, size={disk.size_bytes // (1024**3):.1f} GiB, "
            f"secure_boot={secure_boot}, reserve_mb={reserve_mb})"
        )
        append_audit("usb_create", disk.id, "dry_run", args=audit_args)
        return

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Installing Ventoy...", total=100)

        def _on_progress(pct: int) -> None:
            progress.update(task, completed=pct)

        try:
            install_to_disk(
                disk,
                secure_boot=secure_boot,
                reserve_mb=reserve_mb,
                dry_run=False,
                on_progress=_on_progress,
            )
        except UnsupportedHostError as exc:
            err_console.print(f"[red]ERROR:[/red] {exc}")
            append_audit("usb_create", disk.id, "failure", args=audit_args, error=str(exc))
            raise typer.Exit(2) from exc
        except Exception as exc:  # noqa: BLE001
            err_console.print(f"[red]ERROR:[/red] Ventoy install failed: {exc}")
            append_audit("usb_create", disk.id, "failure", args=audit_args, error=str(exc))
            raise typer.Exit(1) from exc

    console.print(f"[green]Ventoy installed successfully on {disk.path}.[/green]")
    console.print("Copy ISO files to the disk root to make them bootable.")
    append_audit("usb_create", disk.id, "success", args=audit_args)


@app.command("update")
def usb_update(
    ctx: typer.Context,
    device: str = typer.Option(
        ...,
        "--device",
        "-d",
        help="Disk ID or device path of an existing Ventoy USB.",
    ),
    confirm: bool = typer.Option(
        False,
        "--confirm",
        help="Skip the interactive confirmation prompt.",
    ),
    no_banner: bool = typer.Option(
        False,
        "--no-banner",
        hidden=True,
        help="Skip countdown banner (CI/automation use only).",
    ),
) -> None:
    """Update Ventoy on an existing Ventoy USB disk."""
    from sysinstall.cli import merge_global_flags
    from sysinstall.safety import SafetyError, check_destructive
    from sysinstall.safety.prompts import confirm_with_banner
    from sysinstall.ventoy import UnsupportedHostError, update

    if sys.platform == "darwin":
        from sysinstall.ventoy import MACOS_VENTOY_MESSAGE
        err_console.print(f"[red]ERROR:[/red] {MACOS_VENTOY_MESSAGE}")
        raise typer.Exit(2)

    disk = _resolve_disk(device)

    flags = merge_global_flags(ctx, confirm=confirm)

    try:
        check_destructive(disk, "usb_update")
    except SafetyError as exc:
        err_console.print(f"[red]ERROR:[/red] {exc}")
        if exc.suggestion:
            err_console.print(f"[yellow]Hint:[/yellow] {exc.suggestion}")
        raise typer.Exit(2) from exc

    confirm_with_banner(
        disk,
        "usb_update",
        "update Ventoy",
        confirmed=flags["confirm"],
        no_banner=no_banner,
    )

    append_audit("usb_update", disk.id, "started")

    try:
        update(disk)
    except UnsupportedHostError as exc:
        err_console.print(f"[red]ERROR:[/red] {exc}")
        append_audit("usb_update", disk.id, "failure", error=str(exc))
        raise typer.Exit(2) from exc
    except Exception as exc:  # noqa: BLE001
        err_console.print(f"[red]ERROR:[/red] Ventoy update failed: {exc}")
        append_audit("usb_update", disk.id, "failure", error=str(exc))
        raise typer.Exit(1) from exc

    console.print(f"[green]Ventoy updated successfully on {disk.path}.[/green]")
    append_audit("usb_update", disk.id, "success")


@app.command("info")
def usb_info(
    device: str = typer.Option(
        ...,
        "--device",
        "-d",
        help="Disk ID or device path to inspect.",
    ),
) -> None:
    """Show Ventoy installation status on a disk."""
    from sysinstall.ventoy import is_installed

    disk = _resolve_disk(device)
    installed = is_installed(disk)

    console.print(f"Device : {disk.path}")
    console.print(f"Model  : {disk.model}")
    console.print(f"Serial : {disk.serial or 'unknown'}")
    console.print(f"Size   : {disk.size_bytes / (1024**3):.1f} GiB")
    console.print(
        f"Ventoy : {'[green]installed[/green]' if installed else '[yellow]not detected[/yellow]'}"
    )
