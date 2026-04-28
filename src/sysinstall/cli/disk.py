"""Disk subcommand group — list, show, and partition physical disks."""

from __future__ import annotations

import json
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from sysinstall.disks import BackendUnavailable, get_disk, list_disks
from sysinstall.disks.base import Disk

app = typer.Typer(help="Disk enumeration and inspection commands.")
console = Console()
err_console = Console(stderr=True)

_SIZE_UNITS = [("TB", 1024**4), ("GB", 1024**3), ("MB", 1024**2), ("KB", 1024)]


def _human_size(size_bytes: int) -> str:
    for unit, threshold in _SIZE_UNITS:
        if size_bytes >= threshold:
            return f"{size_bytes / threshold:.1f} {unit}"
    return f"{size_bytes} B"


def _disk_to_dict(disk: Disk) -> dict[str, object]:
    return {
        "id": disk.id,
        "path": disk.path,
        "size_bytes": disk.size_bytes,
        "size_human": _human_size(disk.size_bytes),
        "model": disk.model,
        "serial": disk.serial,
        "bus": disk.bus,
        "is_removable": disk.is_removable,
        "is_system": disk.is_system,
        "partitions": [
            {
                "id": p.id,
                "fs_type": p.fs_type,
                "size_bytes": p.size_bytes,
                "size_human": _human_size(p.size_bytes),
                "mountpoints": list(p.mountpoints),
                "label": p.label,
            }
            for p in disk.partitions
        ],
    }


@app.command("list")
def disk_list(
    as_json: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON instead of a table."),
    ] = False,
) -> None:
    """List all physical disks detected on this host."""
    try:
        disks = list_disks()
    except BackendUnavailable as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1) from exc

    if not disks:
        if as_json:
            typer.echo("[]")
        else:
            console.print("No physical disks found.")
        return

    if as_json:
        typer.echo(json.dumps([_disk_to_dict(d) for d in disks], indent=2))
        return

    table = Table(title="Physical Disks", show_lines=False)
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Path", style="dim")
    table.add_column("Size", justify="right")
    table.add_column("Model")
    table.add_column("Bus")
    table.add_column("Removable", justify="center")
    table.add_column("System", justify="center")

    for disk in disks:
        table.add_row(
            disk.id,
            disk.path,
            _human_size(disk.size_bytes),
            disk.model,
            disk.bus,
            "yes" if disk.is_removable else "no",
            "[bold green]YES[/bold green]" if disk.is_system else "no",
        )

    console.print(table)


@app.command("show")
def disk_show(
    disk_id: Annotated[str, typer.Argument(help="Stable disk ID from 'disk list'.")],
    as_json: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON."),
    ] = False,
) -> None:
    """Show detailed information for a specific disk, including partitions."""
    try:
        disk = get_disk(disk_id)
    except BackendUnavailable as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1) from exc
    except KeyError as exc:
        err_console.print(f"[red]Disk not found:[/red] {disk_id}")
        raise typer.Exit(1) from exc

    if as_json:
        typer.echo(json.dumps(_disk_to_dict(disk), indent=2))
        return

    console.print(f"\n[bold]Disk:[/bold] {disk.id}")
    console.print(f"  Path:      {disk.path}")
    console.print(f"  Model:     {disk.model}")
    console.print(f"  Serial:    {disk.serial or '(none)'}")
    console.print(f"  Size:      {_human_size(disk.size_bytes)} ({disk.size_bytes:,} bytes)")
    console.print(f"  Bus:       {disk.bus}")
    console.print(f"  Removable: {'yes' if disk.is_removable else 'no'}")
    console.print(f"  System:    {'yes' if disk.is_system else 'no'}")

    if not disk.partitions:
        console.print("\n  [dim]No partitions found.[/dim]")
        return

    part_table = Table(title=f"Partitions on {disk.path}", show_lines=False)
    part_table.add_column("ID", style="cyan", no_wrap=True)
    part_table.add_column("FS Type")
    part_table.add_column("Size", justify="right")
    part_table.add_column("Mountpoints")
    part_table.add_column("Label")

    for part in disk.partitions:
        mps = ", ".join(part.mountpoints) if part.mountpoints else ""
        part_table.add_row(
            part.id,
            part.fs_type or "",
            _human_size(part.size_bytes),
            mps,
            part.label or "",
        )

    console.print()
    console.print(part_table)


# ---------------------------------------------------------------------------
# partition subcommand
# ---------------------------------------------------------------------------


@app.command("partition")
def disk_partition(
    ctx: typer.Context,
    device: Annotated[
        str,
        typer.Option("--device", help="Stable disk ID from 'disk list'."),
    ],
    layout: Annotated[
        str,
        typer.Option("--layout", help="Partition layout preset. Only 'dual-boot' is supported."),
    ] = "dual-boot",
    windows_size: Annotated[
        int,
        typer.Option("--windows-size", help="Windows partition size in GiB (minimum 30)."),
    ] = 100,
    swap_size: Annotated[
        int,
        typer.Option("--swap-size", help="Linux swap partition size in GiB (0–32)."),
    ] = 4,
    no_swap: Annotated[
        bool,
        typer.Option("--no-swap", help="Omit the swap partition entirely."),
    ] = False,
    allow_encrypted: Annotated[
        bool,
        typer.Option("--allow-encrypted", help="Proceed even if disk appears encrypted (audited)."),
    ] = False,
    allow_fixed_disk: Annotated[
        bool,
        typer.Option("--allow-fixed-disk", help="Allow partitioning non-removable disks."),
    ] = False,
    force_encrypted: Annotated[
        bool,
        typer.Option("--force-encrypted", help="Proceed on encrypted disks with a warning."),
    ] = False,
    auto_unmount: Annotated[
        bool,
        typer.Option("--auto-unmount", help="Auto-unmount mounted partitions before partitioning."),
    ] = False,
    confirm: Annotated[
        bool,
        typer.Option("--confirm", help="Skip interactive confirmation prompt."),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Print planned commands without executing them."),
    ] = False,
    as_json: Annotated[
        bool,
        typer.Option("--json", help="Output planned partition table as JSON and exit."),
    ] = False,
    no_banner: Annotated[
        bool,
        typer.Option("--no-banner", hidden=True, help="Skip countdown banner (CI only)."),
    ] = False,
) -> None:
    """Partition a disk for dual-boot (ESP + MSR + Windows + Ubuntu + swap).

    WARNING: ALL DATA ON THE TARGET DISK WILL BE ERASED. Back up first.
    """
    from sysinstall.cli import merge_global_flags
    from sysinstall.partition import apply, plan
    from sysinstall.partition.layout import DualBootLayout, LayoutValidationError
    from sysinstall.safety import SafetyError, check_destructive
    from sysinstall.safety.prompts import confirm_with_banner

    if layout != "dual-boot":
        err_console.print(f"[red]Error:[/red] Unsupported layout {layout!r}. Only 'dual-boot' is supported.")
        raise typer.Exit(1)

    # Resolve disk
    try:
        disk = get_disk(device)
    except BackendUnavailable as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1) from exc
    except KeyError as exc:
        err_console.print(f"[red]Disk not found:[/red] {device}")
        raise typer.Exit(1) from exc

    # Merge global flags with local flags.
    # --allow-encrypted maps to force_encrypted for the gate pipeline.
    flags = merge_global_flags(
        ctx,
        confirm=confirm,
        dry_run=dry_run,
        allow_fixed_disk=allow_fixed_disk,
        force_encrypted=force_encrypted or allow_encrypted,
        auto_unmount=auto_unmount,
    )

    # Unified safety gate pipeline — system-disk has NO override.
    try:
        check_destructive(
            disk,
            "disk_partition",
            allow_fixed=flags["allow_fixed_disk"],
            force_encrypted=flags["force_encrypted"],
            auto_unmount=flags["auto_unmount"],
        )
    except SafetyError as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        if exc.suggestion:
            err_console.print(f"[yellow]Hint:[/yellow] {exc.suggestion}")
        raise typer.Exit(2) from exc

    # Build layout
    effective_swap = 0 if no_swap else swap_size
    try:
        disk_layout = DualBootLayout(
            windows_size_gb=windows_size,
            swap_size_gb=effective_swap,
            disk_size_bytes=disk.size_bytes,
        )
    except LayoutValidationError as exc:
        err_console.print(f"[red]Layout error:[/red] {exc}")
        raise typer.Exit(1) from exc

    # Compute plan (pure)
    partition_plan = plan(disk, disk_layout)

    # JSON output mode — print and exit
    if as_json:
        output = {
            "disk": {
                "id": disk.id,
                "path": disk.path,
                "model": disk.model,
                "serial": disk.serial,
                "size_bytes": disk.size_bytes,
                "bus": disk.bus,
            },
            "partitions": [
                {
                    "index": p.index,
                    "label": p.label,
                    "size_mb": p.size_mb,
                    "fs": p.fs,
                    "type_guid": p.type_guid,
                    "mountpoint_hint": p.mountpoint_hint,
                }
                for p in partition_plan.partitions
            ],
            "total_required_mb": partition_plan.total_required_mb,
        }
        typer.echo(json.dumps(output, indent=2))
        return

    # Display disk header
    console.print()
    console.print(
        f"[bold]Disk:[/bold] {disk.model or '(unknown)'} | "
        f"Serial: {disk.serial or '(none)'} | "
        f"Size: {_human_size(disk.size_bytes)} | "
        f"Bus: {disk.bus}"
    )
    console.print(f"[bold]Path:[/bold] {disk.path}  [bold]ID:[/bold] {disk.id}")
    console.print()

    # Display planned partition table
    part_table = Table(title="Planned Partition Layout", show_lines=True)
    part_table.add_column("#", style="cyan", justify="right")
    part_table.add_column("Label")
    part_table.add_column("Size", justify="right")
    part_table.add_column("FS")
    part_table.add_column("Mountpoint hint")

    for p in partition_plan.partitions:
        size_str = _human_size(p.size_mb * 1024 * 1024) if p.size_mb else "remaining"
        part_table.add_row(
            str(p.index),
            p.label,
            size_str,
            p.fs,
            p.mountpoint_hint or "",
        )

    console.print(part_table)
    console.print()

    # Red-banner confirm with countdown (respects global flags).
    confirm_with_banner(
        disk,
        "disk_partition",
        f"partition disk for dual-boot (windows={windows_size}GiB, swap={effective_swap}GiB)",
        confirmed=flags["confirm"],
        no_banner=no_banner,
    )

    # Execute / dry-run
    progress_lines: list[str] = []

    def _on_progress(msg: str) -> None:
        progress_lines.append(msg)
        console.print(f"  [dim]{msg}[/dim]")

    try:
        apply(
            partition_plan,
            dry_run=flags["dry_run"],
            allow_encrypted=flags["force_encrypted"],
            on_progress=_on_progress,
        )
    except RuntimeError as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1) from exc

    if flags["dry_run"]:
        console.print("[yellow]Dry-run complete — no disk changes were made.[/yellow]")
    else:
        console.print("[green]Partitioning complete.[/green]")
