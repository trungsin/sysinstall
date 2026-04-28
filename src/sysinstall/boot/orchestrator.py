"""Boot repair orchestration — wires together chroot, grub, efi, backup.

Two paths:
  run_manual_repair  — default, auditable chroot path
  run_boot_repair_tool — fast path via boot-repair package (--use-boot-repair)

Both are called from the public repair() function in __init__.py.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from sysinstall.boot.chroot import ChrootContext
from sysinstall.boot.efi import find_ubuntu_first_order, list_entries, set_boot_order
from sysinstall.boot.grub import enable_os_prober, install_bios, install_uefi, update_grub
from sysinstall.boot.types import RepairPlan
from sysinstall.safety.audit import append_audit

log = logging.getLogger(__name__)

ProgressCallback = Callable[[str], None]

_BOOT_REPAIR_TIMEOUT = 300


def _noop(msg: str) -> None:  # pragma: no cover
    pass


def run_boot_repair_tool(
    *,
    dry_run: bool = False,
    on_progress: ProgressCallback | None = None,
) -> None:
    """Fast path: delegate to the boot-repair package non-interactively.

    boot-repair must already be installed on the system. If not found,
    raises FileNotFoundError — caller should exit 2 with install instructions.

    Args:
        dry_run: Log intent but do not execute.
        on_progress: Optional callback receiving progress strings.

    Raises:
        FileNotFoundError: boot-repair binary not found on PATH.
        RuntimeError: boot-repair exited non-zero.
    """
    cb = on_progress or _noop
    tool = shutil.which("boot-repair")
    if tool is None:
        raise FileNotFoundError(
            "boot-repair is not installed. Install it with:\n"
            "  sudo add-apt-repository ppa:yannubuntu/boot-repair\n"
            "  sudo apt update && sudo apt install -y boot-repair"
        )

    args = [tool, "--no-gui"]
    append_audit(
        "boot.repair.start",
        target="boot-repair",
        outcome="dry_run" if dry_run else "started",
        args={"cmd": " ".join(args)},
    )
    cb("Running boot-repair (this may take a while)...")

    if dry_run:
        log.info("[dry-run] would run: %s", " ".join(args))
        return

    result = subprocess.run(args, capture_output=True, timeout=_BOOT_REPAIR_TIMEOUT)
    stdout = result.stdout.decode(errors="replace")
    if stdout:
        for line in stdout.splitlines():
            cb(line)

    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace").strip()
        append_audit(
            "boot.repair.failure", target="boot-repair", outcome="failure", error=stderr
        )
        raise RuntimeError(f"boot-repair exited {result.returncode}: {stderr}")

    append_audit("boot.repair.success", target="boot-repair", outcome="success")
    cb("boot-repair completed successfully.")


def run_manual_repair(
    plan: RepairPlan,
    *,
    dry_run: bool = False,
    on_progress: ProgressCallback | None = None,
) -> None:
    """Default repair path: chroot + grub-install + update-grub + efibootmgr.

    Steps:
      1. Set up ChrootContext (root + ESP + bind mounts)
      2. Optionally enable os-prober in chroot's /etc/default/grub
      3. Run grub-install (UEFI or BIOS target)
      4. Run update-grub
      5. If UEFI + set_boot_order_first: reorder EFI entries Ubuntu-first

    Args:
        plan: RepairPlan describing what to do.
        dry_run: Log all steps but skip destructive subprocess calls.
        on_progress: Optional callback receiving progress strings.

    Raises:
        RuntimeError: if any subprocess step fails.
    """
    cb = on_progress or _noop

    root_part = plan.root_partition
    efi_part = plan.efi_partition  # None for BIOS mode

    append_audit(
        "boot.repair.start",
        target=root_part.id,
        outcome="dry_run" if dry_run else "started",
        args={
            "firmware": plan.firmware,
            "efi_part": efi_part.id if efi_part else None,
            "enable_os_prober": plan.enable_os_prober,
            "set_boot_order_first": plan.set_boot_order_first,
        },
    )

    cb(f"Setting up chroot on {root_part.id}...")
    with ChrootContext(root_part, efi_part, dry_run=dry_run) as chroot_root:
        _repair_inside_chroot(plan, chroot_root, dry_run=dry_run, on_progress=cb)

    # EFI boot order adjustment runs outside the chroot.
    if plan.firmware == "uefi" and plan.set_boot_order_first:
        _adjust_boot_order(dry_run=dry_run, on_progress=cb)

    append_audit(
        "boot.repair.success",
        target=root_part.id,
        outcome="dry_run" if dry_run else "success",
    )
    cb("Boot repair completed successfully.")


def _repair_inside_chroot(
    plan: RepairPlan,
    chroot_root: Path,
    *,
    dry_run: bool,
    on_progress: ProgressCallback,
) -> None:
    """Execute grub steps inside an already-set-up chroot."""
    if plan.enable_os_prober:
        on_progress("Enabling os-prober in grub config...")
        enable_os_prober(chroot_root, dry_run=dry_run)

    if plan.firmware == "uefi":
        on_progress("Installing GRUB (UEFI)...")
        install_uefi(chroot_root, dry_run=dry_run)
    else:
        # BIOS mode: need the whole disk, not just the partition.
        # Derive disk path by stripping trailing digit(s) from partition path.
        disk_path = _derive_disk_path(plan.root_partition.id)
        on_progress(f"Installing GRUB (BIOS) on {disk_path}...")
        install_bios(chroot_root, Path(disk_path), dry_run=dry_run)

    on_progress("Running update-grub...")
    update_grub(chroot_root, dry_run=dry_run)


def _derive_disk_path(partition_id: str) -> str:
    """Derive a whole-disk path from a partition device path.

    Examples:
      /dev/sda3  -> /dev/sda
      /dev/nvme0n1p2 -> /dev/nvme0n1

    Falls back to the partition_id unchanged if pattern not recognised.
    """
    import re
    # NVMe: strip trailing pN
    nvme = re.match(r"^(/dev/nvme\d+n\d+)p\d+$", partition_id)
    if nvme:
        return nvme.group(1)
    # SCSI/SATA: strip trailing digit(s)
    scsi = re.match(r"^(/dev/sd[a-z]+)\d+$", partition_id)
    if scsi:
        return scsi.group(1)
    log.warning("Could not derive disk path from %s — using as-is", partition_id)
    return partition_id


def _adjust_boot_order(*, dry_run: bool, on_progress: ProgressCallback) -> None:
    """Query efibootmgr and move Ubuntu entry to top of boot order."""
    on_progress("Adjusting EFI boot order (Ubuntu first)...")
    try:
        entries = list_entries()
        reordered = find_ubuntu_first_order(entries)
        set_boot_order(reordered, dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001
        # Non-fatal — boot order adjustment failure doesn't break the repair.
        log.warning("Could not adjust EFI boot order: %s", exc)
        on_progress(f"Warning: could not adjust boot order: {exc}")
