"""Rich red-banner confirm prompts with countdown and rate-limit cache.

Public API:
    show_destructive_banner(disk, ops_summary, *, confirmed, no_banner) -> None
    confirm_with_banner(disk, op, *, confirmed, no_banner) -> None

Rate-limit: in-memory dict keyed by (disk_id, op) -> last-prompt timestamp.
Two calls for same (disk, op) within 60 s auto-pass (no second prompt).

Countdown: 5-second Rich Progress countdown before each destructive op.
Skippable only with --no-banner (undocumented CI flag).
--confirm alone does NOT skip the countdown.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import typer
from rich.console import Console
from rich.panel import Panel

if TYPE_CHECKING:
    from sysinstall.disks.base import Disk

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_console = Console(stderr=True)

# Rate-limit cache: (disk_id, op) -> epoch timestamp of last prompt shown.
_rate_limit_cache: dict[tuple[str, str], float] = {}

# Seconds before the same (disk, op) prompt is shown again.
_RATE_LIMIT_SECONDS = 60

# Countdown duration in seconds (one tick per second).
_COUNTDOWN_SECONDS = 5


# ---------------------------------------------------------------------------
# Rate-limit helpers
# ---------------------------------------------------------------------------


def _is_rate_limited(disk_id: str, op: str) -> bool:
    """Return True if a prompt for (disk_id, op) was shown within the limit window."""
    key = (disk_id, op)
    last = _rate_limit_cache.get(key)
    if last is None:
        return False
    return (time.monotonic() - last) < _RATE_LIMIT_SECONDS


def _record_prompt(disk_id: str, op: str) -> None:
    """Record that a prompt was shown now for (disk_id, op)."""
    _rate_limit_cache[(disk_id, op)] = time.monotonic()


def clear_rate_limit_cache() -> None:
    """Clear the in-memory rate-limit cache (for tests)."""
    _rate_limit_cache.clear()


# ---------------------------------------------------------------------------
# Countdown banner
# ---------------------------------------------------------------------------


def _run_countdown(seconds: int = _COUNTDOWN_SECONDS) -> None:
    """Display a 5-second countdown using Rich Progress, 1 tick per second."""
    from rich.progress import BarColumn, Progress, TextColumn, TimeRemainingColumn

    with Progress(
        TextColumn("[bold red]Starting in"),
        BarColumn(bar_width=20, style="red", complete_style="red"),
        TextColumn("[bold red]{task.fields[secs]}s"),
        TimeRemainingColumn(),
        console=_console,
        transient=True,
    ) as progress:
        task = progress.add_task("countdown", total=seconds, secs=seconds)
        for remaining in range(seconds, 0, -1):
            progress.update(task, completed=seconds - remaining, secs=remaining)
            time.sleep(1)
        progress.update(task, completed=seconds, secs=0)


# ---------------------------------------------------------------------------
# Banner display
# ---------------------------------------------------------------------------


def show_destructive_banner(
    disk: Disk,
    ops_summary: str,
    *,
    no_banner: bool = False,
) -> None:
    """Show a Rich red-bordered panel with disk info and planned ops.

    Args:
        disk: Target disk being operated on.
        ops_summary: Short description of the planned operation(s).
        no_banner: If True, skip both the banner and countdown (CI/automation).
    """
    if no_banner:
        return

    size_gib = disk.size_bytes / (1024 ** 3)
    content = (
        f"[bold]Device :[/bold]  {disk.path}\n"
        f"[bold]Model  :[/bold]  {disk.model}\n"
        f"[bold]Serial :[/bold]  {disk.serial or 'unknown'}\n"
        f"[bold]Size   :[/bold]  {size_gib:.1f} GiB\n"
        f"[bold]ID     :[/bold]  {disk.id}\n"
        f"\n"
        f"[bold]Planned:[/bold]  {ops_summary}\n"
        f"\n"
        f"[bold red]ALL DATA ON THIS DISK WILL BE PERMANENTLY ERASED.[/bold red]\n"
        f"[bold red]There is no undo. Ensure you have a complete backup.[/bold red]"
    )
    _console.print(
        Panel(
            content,
            title="[bold red]DESTRUCTIVE OPERATION[/bold red]",
            border_style="red",
            expand=False,
        )
    )
    _run_countdown()


# ---------------------------------------------------------------------------
# Main public entry point
# ---------------------------------------------------------------------------


def confirm_with_banner(
    disk: Disk,
    op: str,
    ops_summary: str | None = None,
    *,
    confirmed: bool = False,
    no_banner: bool = False,
) -> None:
    """Show banner, countdown, then interactive prompt (respects rate-limit and --confirm).

    Args:
        disk: Target disk.
        op: Short operation name used as rate-limit key and audit label.
        ops_summary: Human-readable summary of what will happen (default: op).
        confirmed: If True (--confirm flag), skip the interactive y/N prompt.
            Does NOT skip countdown unless no_banner is also True.
        no_banner: If True (--no-banner flag), skip banner AND countdown.
            Intended for CI/automation only.

    Raises:
        typer.Abort: user declined at the interactive prompt.
    """
    summary = ops_summary or op

    # Show banner + countdown (unless --no-banner)
    show_destructive_banner(disk, summary, no_banner=no_banner)

    # Rate-limit: if we already prompted for this (disk, op) recently, auto-pass.
    if _is_rate_limited(disk.id, op):
        return

    _record_prompt(disk.id, op)

    if confirmed:
        _console.print(
            "[yellow]Proceeding automatically (--confirm flag passed).[/yellow]"
        )
        return

    # Interactive prompt
    response = typer.prompt(
        "This will ERASE ALL DATA. Type 'yes' to continue",
        default="no",
    )
    if response.strip().lower() != "yes":
        typer.echo("Aborted.")
        raise typer.Abort()
