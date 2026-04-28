"""GRUB installation and configuration helpers.

All functions build subprocess argument lists and execute them.
Pure builder functions (returning arg lists) are tested directly;
execution functions call subprocess with those lists.

enable_os_prober is a pure string transform — no subprocess, testable.
"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

from sysinstall.safety.audit import append_audit

log = logging.getLogger(__name__)

# Timeout for grub-install (can be slow on slow disks)
_GRUB_INSTALL_TIMEOUT = 600
_UPDATE_GRUB_TIMEOUT = 120

# Regex to match any GRUB_DISABLE_OS_PROBER line (commented or active)
_OS_PROBER_RE = re.compile(
    r"^#?\s*GRUB_DISABLE_OS_PROBER\s*=.*$",
    re.MULTILINE,
)


# ---------------------------------------------------------------------------
# Pure command builders (tested without subprocess)
# ---------------------------------------------------------------------------


def _uefi_install_args(chroot_root: Path) -> list[str]:
    return [
        "chroot",
        str(chroot_root),
        "grub-install",
        "--target=x86_64-efi",
        "--efi-directory=/boot/efi",
        "--bootloader-id=ubuntu",
    ]


def _bios_install_args(chroot_root: Path, disk: Path) -> list[str]:
    return [
        "chroot",
        str(chroot_root),
        "grub-install",
        "--target=i386-pc",
        str(disk),
    ]


def _update_grub_args(chroot_root: Path) -> list[str]:
    return ["chroot", str(chroot_root), "update-grub"]


# ---------------------------------------------------------------------------
# Execution helpers
# ---------------------------------------------------------------------------


def _run(args: list[str], *, timeout: int, action: str, target: str, dry_run: bool) -> None:
    """Run a subprocess command with audit logging."""
    append_audit(
        action,
        target=target,
        outcome="dry_run" if dry_run else "started",
        args={"cmd": " ".join(args)},
    )
    if dry_run:
        log.info("[dry-run] would run: %s", " ".join(args))
        return

    result = subprocess.run(args, capture_output=True, timeout=timeout)
    stderr = result.stderr.decode(errors="replace").strip()
    stdout = result.stdout.decode(errors="replace").strip()
    if stdout:
        log.debug("%s stdout: %s", args[0], stdout)

    if result.returncode != 0:
        append_audit(action, target=target, outcome="failure", error=stderr)
        raise RuntimeError(
            f"{args[0]} failed (exit {result.returncode}): {stderr}"
        )
    append_audit(action, target=target, outcome="success")
    log.info("%s completed successfully", " ".join(args[:3]))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def install_uefi(chroot_root: Path, *, dry_run: bool = False) -> None:
    """Install GRUB for UEFI boot inside the chroot.

    Args:
        chroot_root: Path to the mounted chroot root (e.g. /tmp/sysinstall-chroot-xxx).
        dry_run: Log command but do not execute.
    """
    args = _uefi_install_args(chroot_root)
    _run(
        args,
        timeout=_GRUB_INSTALL_TIMEOUT,
        action="boot.repair.command",
        target=str(chroot_root),
        dry_run=dry_run,
    )


def install_bios(chroot_root: Path, disk: Path, *, dry_run: bool = False) -> None:
    """Install GRUB for BIOS/MBR boot inside the chroot.

    Args:
        chroot_root: Path to the mounted chroot root.
        disk: Whole disk device path (e.g. /dev/sda).
        dry_run: Log command but do not execute.
    """
    args = _bios_install_args(chroot_root, disk)
    _run(
        args,
        timeout=_GRUB_INSTALL_TIMEOUT,
        action="boot.repair.command",
        target=str(disk),
        dry_run=dry_run,
    )


def update_grub(chroot_root: Path, *, dry_run: bool = False) -> None:
    """Run update-grub inside the chroot to regenerate grub.cfg.

    Args:
        chroot_root: Path to the mounted chroot root.
        dry_run: Log command but do not execute.
    """
    args = _update_grub_args(chroot_root)
    _run(
        args,
        timeout=_UPDATE_GRUB_TIMEOUT,
        action="boot.repair.command",
        target=str(chroot_root),
        dry_run=dry_run,
    )


def enable_os_prober(chroot_root: Path, *, dry_run: bool = False) -> None:
    """Set GRUB_DISABLE_OS_PROBER=false in /etc/default/grub inside chroot.

    Handles three cases:
    1. Line present and set to any value -> replace with GRUB_DISABLE_OS_PROBER=false
    2. Line commented out (#GRUB_DISABLE_OS_PROBER=...) -> uncomment and set
    3. Line absent -> append GRUB_DISABLE_OS_PROBER=false

    Uses Path.read_text / write_text — no shell sed call.

    Args:
        chroot_root: Path to the mounted chroot root.
        dry_run: Log intent but do not write file.
    """
    grub_cfg = chroot_root / "etc" / "default" / "grub"

    append_audit(
        "boot.repair.command",
        target=str(grub_cfg),
        outcome="dry_run" if dry_run else "started",
        args={"action": "enable_os_prober"},
    )

    if dry_run:
        log.info("[dry-run] would set GRUB_DISABLE_OS_PROBER=false in %s", grub_cfg)
        return

    if not grub_cfg.exists():
        log.warning("grub config not found at %s — skipping os-prober toggle", grub_cfg)
        return

    original = grub_cfg.read_text(encoding="utf-8")
    new_line = "GRUB_DISABLE_OS_PROBER=false"

    if _OS_PROBER_RE.search(original):
        updated = _OS_PROBER_RE.sub(new_line, original)
    else:
        # Append with a newline separator
        updated = original.rstrip("\n") + "\n" + new_line + "\n"

    grub_cfg.write_text(updated, encoding="utf-8")
    log.info("Set GRUB_DISABLE_OS_PROBER=false in %s", grub_cfg)


def toggle_os_prober_text(content: str) -> str:
    """Pure transform: set GRUB_DISABLE_OS_PROBER=false in grub config text.

    This is the testable core of enable_os_prober — operates on strings only.

    Args:
        content: Full text content of /etc/default/grub.

    Returns:
        Updated text with GRUB_DISABLE_OS_PROBER=false set.
    """
    new_line = "GRUB_DISABLE_OS_PROBER=false"
    if _OS_PROBER_RE.search(content):
        return _OS_PROBER_RE.sub(new_line, content)
    return content.rstrip("\n") + "\n" + new_line + "\n"
