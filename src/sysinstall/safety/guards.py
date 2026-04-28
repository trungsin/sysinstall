"""Disk operation safety guards.

All guards raise SystemExit(2) with a human-readable message on refusal,
matching Typer's convention for usage errors so the CLI exits with code 2.

validate_disk_path uses a strict allowlist regex — anything that does not
match is rejected before it ever reaches a subprocess call.
"""

from __future__ import annotations

import re

import typer

from sysinstall.disks.base import Disk

# Allowlist: Linux sd*, Linux NVMe, macOS disk*, Windows PhysicalDrive.
_DISK_PATH_RE = re.compile(
    r"^/dev/sd[a-z]+$"          # Linux SCSI/SATA/USB
    r"|^/dev/nvme\d+n\d+$"      # Linux NVMe
    r"|^/dev/disk\d+$"          # macOS (for listing only)
    r"|^\\\\\.\\"               # Windows \\.\PhysicalDriveN prefix
    r"PhysicalDrive\d+$"
)


def validate_disk_path(path: str) -> None:
    """Raise typer.BadParameter if *path* does not match the allowlist regex.

    Args:
        path: Raw device path string to validate.

    Raises:
        typer.BadParameter: path does not match the expected pattern.
    """
    if not _DISK_PATH_RE.match(path):
        raise typer.BadParameter(
            f"Device path {path!r} is not a recognised block device pattern. "
            "Expected e.g. /dev/sdb, /dev/nvme0n1, or \\\\.\\PhysicalDrive1."
        )


def refuse_if_system(disk: Disk) -> None:
    """Abort with exit code 2 if *disk* is the system disk.

    This check is hardcoded and has no override flag — protecting the
    running OS disk from accidental erasure is non-negotiable.

    Args:
        disk: Disk to inspect.

    Raises:
        typer.Exit(2): disk.is_system is True.
    """
    if disk.is_system:
        typer.echo(
            f"ERROR: Refusing to touch system disk {disk.path} "
            f"(model={disk.model!r}, id={disk.id!r}). "
            "This disk appears to contain the running OS. "
            "No override flag exists for this check.",
            err=True,
        )
        raise typer.Exit(2)


def refuse_if_fixed(disk: Disk, *, allow_fixed: bool) -> None:
    """Abort with exit code 2 if *disk* is non-removable and allow_fixed is False.

    Args:
        disk: Disk to inspect.
        allow_fixed: Pass True (via --allow-fixed-disk flag) to skip this check.

    Raises:
        typer.Exit(2): disk.is_removable is False and allow_fixed is False.
    """
    if not disk.is_removable and not allow_fixed:
        typer.echo(
            f"ERROR: {disk.path} (model={disk.model!r}) is not a removable disk. "
            "Pass --allow-fixed-disk to override this check (use with extreme caution).",
            err=True,
        )
        raise typer.Exit(2)


def confirm_destructive(disk: Disk, action: str, *, confirmed: bool = False) -> None:
    """Prompt the user to confirm a destructive action, or accept via --confirm flag.

    Prints disk model, serial, size, and path before asking.

    Args:
        disk: Target disk.
        action: Short description, e.g. "install Ventoy".
        confirmed: If True (--confirm flag passed), skip the interactive prompt.

    Raises:
        typer.Abort: user declined at the interactive prompt.
    """
    size_gib = disk.size_bytes / (1024 ** 3)
    summary = (
        f"  Device : {disk.path}\n"
        f"  Model  : {disk.model}\n"
        f"  Serial : {disk.serial or 'unknown'}\n"
        f"  Size   : {size_gib:.1f} GiB\n"
        f"  ID     : {disk.id}"
    )

    if confirmed:
        typer.echo(
            f"WARNING: About to {action} on:\n{summary}\n"
            "(proceeding automatically — --confirm flag was passed)"
        )
        return

    typer.echo(f"\nAbout to {action} on:\n{summary}\n")
    response = typer.prompt(
        "This will ERASE ALL DATA on the disk. Type 'yes' to continue",
        default="no",
    )
    if response.strip().lower() != "yes":
        typer.echo("Aborted.")
        raise typer.Abort()
