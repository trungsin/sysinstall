"""ISO subcommand group: list, add, remove, verify.

All subcommands require --device <disk-id>.
add and verify display Rich progress bars.
list and verify support --json for machine-readable output.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, TaskID, TextColumn, TransferSpeedColumn
from rich.table import Table

from sysinstall import disks as disk_api
from sysinstall.disks.base import Disk
from sysinstall.iso import (
    InsufficientSpaceError,
    ManagedIso,
    NotAVentoyUSBError,
    VerifyResult,
    add_iso,
    list_isos,
    remove_iso,
    verify_isos,
)

log = logging.getLogger(__name__)

app = typer.Typer(help="ISO image management on a Ventoy USB.")

console = Console()
err_console = Console(stderr=True)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _resolve_disk(device: str) -> Disk:
    """Resolve disk by ID; exit with error on unknown device."""
    try:
        return disk_api.get_disk(device)
    except KeyError:
        err_console.print(f"[red]ERROR:[/red] Unknown device {device!r}. "
                          "Run 'sysinstall disk list' to see available devices.")
        raise typer.Exit(1) from None
    except Exception as exc:  # noqa: BLE001
        err_console.print(f"[red]ERROR:[/red] {exc}")
        raise typer.Exit(1) from exc


def _handle_common_errors(exc: Exception) -> None:
    """Print a friendly message for known ISO errors and exit."""
    if isinstance(exc, NotAVentoyUSBError):
        err_console.print(f"[red]ERROR:[/red] {exc}")
        raise typer.Exit(1)
    if isinstance(exc, InsufficientSpaceError):
        err_console.print(f"[red]ERROR:[/red] {exc}")
        raise typer.Exit(1)
    if isinstance(exc, ValueError):
        err_console.print(f"[red]ERROR:[/red] {exc}")
        raise typer.Exit(1)
    if isinstance(exc, KeyError):
        err_console.print(f"[red]ERROR:[/red] {exc}")
        raise typer.Exit(1)
    raise exc


def _iso_to_dict(iso: ManagedIso) -> dict[str, object]:
    return {
        "filename": iso.filename,
        "name": iso.name,
        "sha256": iso.sha256,
        "size_bytes": iso.size_bytes,
        "added_at": iso.added_at,
    }


# ---------------------------------------------------------------------------
# list subcommand
# ---------------------------------------------------------------------------

@app.command("list")
def cmd_list(
    device: Annotated[str, typer.Option("--device", "-d", help="Disk ID (from 'disk list').")],
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON array.")] = False,
) -> None:
    """List ISOs managed by sysinstall on a Ventoy USB."""
    disk = _resolve_disk(device)
    try:
        isos = list_isos(disk)
    except Exception as exc:  # noqa: BLE001
        _handle_common_errors(exc)
        return  # unreachable but satisfies type checker

    if as_json:
        typer.echo(json.dumps([_iso_to_dict(i) for i in isos], indent=2, ensure_ascii=False))
        return

    if not isos:
        console.print("[dim]No managed ISOs found on this device.[/dim]")
        return

    table = Table(title=f"Managed ISOs on {device}", show_lines=True)
    table.add_column("Filename", style="cyan")
    table.add_column("Name")
    table.add_column("Size")
    table.add_column("SHA-256 (first 12)")
    table.add_column("Added At")

    for iso in isos:
        size_str = f"{iso.size_bytes / 1024**3:.2f} GiB"
        table.add_row(
            iso.filename,
            iso.name,
            size_str,
            iso.sha256[:12] + "…",
            iso.added_at,
        )

    console.print(table)


# ---------------------------------------------------------------------------
# add subcommand
# ---------------------------------------------------------------------------

@app.command("add")
def cmd_add(
    iso_path: Annotated[Path, typer.Argument(help="Path to the local ISO file.")],
    device: Annotated[str, typer.Option("--device", "-d", help="Disk ID (from 'disk list').")],
    name: Annotated[str | None, typer.Option("--name", "-n", help="Alias name on USB.")] = None,
    checksum: Annotated[
        str | None,
        typer.Option("--checksum", help="Expected SHA-256 hex digest of the source ISO."),
    ] = None,
) -> None:
    """Copy an ISO onto the Ventoy USB and register it in the catalog."""
    disk = _resolve_disk(device)

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.percentage:>3.0f}%"),
        TransferSpeedColumn(),
        console=console,
        transient=True,
    ) as progress:
        task_id: TaskID = progress.add_task("Copying…", total=None)

        def on_progress(done: int, total: int) -> None:
            progress.update(task_id, completed=done, total=total)

        try:
            iso = add_iso(
                disk,
                iso_path,
                name=name,
                expected_sha=checksum,
                on_progress=on_progress,
            )
        except Exception as exc:  # noqa: BLE001
            _handle_common_errors(exc)
            return

    console.print(
        f"[green]Added[/green] {iso.filename} ({iso.size_bytes / 1024**2:.1f} MiB) "
        f"sha256={iso.sha256[:16]}…"
    )


# ---------------------------------------------------------------------------
# remove subcommand
# ---------------------------------------------------------------------------

@app.command("remove")
def cmd_remove(
    identifier: Annotated[str, typer.Argument(help="ISO filename or name alias to remove.")],
    device: Annotated[str, typer.Option("--device", "-d", help="Disk ID (from 'disk list').")],
) -> None:
    """Remove an ISO from the Ventoy USB and the catalog."""
    disk = _resolve_disk(device)
    try:
        removed = remove_iso(disk, identifier)
    except Exception as exc:  # noqa: BLE001
        _handle_common_errors(exc)
        return

    console.print(
        f"[green]Removed[/green] {removed.filename} from {device}."
    )


# ---------------------------------------------------------------------------
# verify subcommand
# ---------------------------------------------------------------------------

@app.command("verify")
def cmd_verify(
    device: Annotated[str, typer.Option("--device", "-d", help="Disk ID (from 'disk list').")],
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON array.")] = False,
) -> None:
    """Re-checksum all managed ISOs and compare against stored hashes."""
    disk = _resolve_disk(device)

    results: list[VerifyResult] = []

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.percentage:>3.0f}%"),
        console=console,
        transient=True,
    ) as progress:
        task_id: TaskID = progress.add_task("Verifying…", total=None)

        def on_progress(done: int, total: int) -> None:
            progress.update(task_id, completed=done, total=total)

        try:
            results = verify_isos(disk, on_progress=on_progress)
        except Exception as exc:  # noqa: BLE001
            _handle_common_errors(exc)
            return

    if as_json:
        out = [
            {
                "filename": r.iso.filename,
                "name": r.iso.name,
                "ok": r.ok,
                "missing": r.missing,
                "stored_sha256": r.iso.sha256,
                "actual_sha256": r.actual_sha256,
            }
            for r in results
        ]
        typer.echo(json.dumps(out, indent=2, ensure_ascii=False))
        return

    if not results:
        console.print("[dim]No managed ISOs to verify.[/dim]")
        return

    all_ok = True
    for r in results:
        if r.missing:
            console.print(f"[yellow]MISSING[/yellow]  {r.iso.filename}")
            all_ok = False
        elif r.ok:
            console.print(f"[green]OK[/green]       {r.iso.filename}")
        else:
            console.print(
                f"[red]FAIL[/red]     {r.iso.filename}  "
                f"expected={r.iso.sha256[:16]}…  actual={r.actual_sha256[:16]}…"
            )
            all_ok = False

    if not all_ok:
        sys.exit(1)
