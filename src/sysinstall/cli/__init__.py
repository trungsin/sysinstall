"""Top-level Typer app — registers subcommand groups and global options.

Global flags (stored on ctx.obj dict, propagated to subcommands):
  --confirm          Skip interactive y/N prompts (not the countdown).
  --dry-run          Log commands instead of executing them.
  --allow-fixed-disk Allow operations on non-removable disks.
  --force-encrypted  Warn-only on encrypted disks instead of refusing.
  --auto-unmount     Auto-unmount mounted partitions before destructive ops.

Per-subcommand flags remain in place for backwards compatibility.
Global flags act as "force on" toggles — if either the global OR local flag
is set, the behaviour is enabled.
"""

from __future__ import annotations

from typing import Any

import typer

from sysinstall import __version__
from sysinstall.cli import boot, disk, iso, usb
from sysinstall.core.logging import configure_logging

app = typer.Typer(
    name="sysinstall",
    help="Multi-boot USB and dual-boot CLI tool.",
    no_args_is_help=True,
    add_completion=False,
)

app.add_typer(disk.app, name="disk")
app.add_typer(usb.app, name="usb")
app.add_typer(iso.app, name="iso")
app.add_typer(boot.app, name="boot")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    version: bool | None = typer.Option(
        None,
        "--version",
        "-V",
        help="Print version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug output."),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress info/warning output."),
    confirm: bool = typer.Option(
        False,
        "--confirm",
        help="Skip interactive confirmation prompts (does not skip countdown banner).",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Log commands without executing any destructive operations.",
    ),
    allow_fixed_disk: bool = typer.Option(
        False,
        "--allow-fixed-disk",
        help="Allow destructive operations on non-removable (fixed) disks.",
    ),
    force_encrypted: bool = typer.Option(
        False,
        "--force-encrypted",
        help="Proceed on encrypted disks with a warning instead of refusing.",
    ),
    auto_unmount: bool = typer.Option(
        False,
        "--auto-unmount",
        help="Automatically unmount mounted partitions before destructive operations.",
    ),
) -> None:
    """sysinstall — multi-boot USB and dual-boot setup tool."""
    configure_logging(verbose=verbose, quiet=quiet)

    # Store global flags on ctx.obj so subcommands can merge them.
    # Subcommands call _merge_global_flags(ctx) to combine local + global.
    ctx.ensure_object(dict)
    obj: dict[str, Any] = ctx.obj
    obj["confirm"] = confirm
    obj["dry_run"] = dry_run
    obj["allow_fixed_disk"] = allow_fixed_disk
    obj["force_encrypted"] = force_encrypted
    obj["auto_unmount"] = auto_unmount


def merge_global_flags(ctx: typer.Context, **local_flags: bool) -> dict[str, bool]:
    """Merge per-subcommand flags with global context flags.

    Either global OR local flag set = behaviour enabled.

    Args:
        ctx: Current Typer context (may be nested; walks up to root).
        **local_flags: Per-subcommand flag values keyed by flag name.

    Returns:
        Dict with merged boolean values for: confirm, dry_run, allow_fixed_disk,
        force_encrypted, auto_unmount.
    """
    # Walk up context chain to find root obj.
    # node is typed as Any to accommodate both typer.Context and click.Context
    # which share the .obj and .parent attributes but differ in their type stubs.
    global_obj: dict[str, Any] = {}
    node: Any = ctx
    while node is not None:
        if isinstance(node.obj, dict):
            global_obj = node.obj
            break
        node = node.parent

    defaults = {
        "confirm": False,
        "dry_run": False,
        "allow_fixed_disk": False,
        "force_encrypted": False,
        "auto_unmount": False,
    }

    merged: dict[str, bool] = {}
    for key, default in defaults.items():
        global_val = bool(global_obj.get(key, default))
        local_val = bool(local_flags.get(key, default))
        merged[key] = global_val or local_val

    return merged
