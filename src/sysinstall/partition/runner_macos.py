"""macOS partition runner — builds and executes diskutil + gpt command sequences.

Command builder (commands()) is pure — no subprocess; fully unit-testable.
Executor (apply()) runs the list and streams progress via on_progress callback.

macOS limitations vs Linux runner:
  - ext4 is not supported on macOS; Ubuntu/swap partitions are left unallocated
    with the correct GPT type GUID so the Ubuntu installer can recognise and
    format them. This is intentional and documented here.
  - NTFS write support (newfs_ntfs) is not a standard macOS component.
    The Windows partition is left unallocated; Windows installer or
    diskpart will format it. macOS does NOT have newfs_ntfs in the base OS.
  - The 'gpt' BSD tool is used for fine-grained GPT slice control after
    diskutil erases the disk.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable

from sysinstall.partition.planner import PartitionPlan, PlannedPartition
from sysinstall.safety.audit import append_audit
from sysinstall.safety.guards import validate_disk_path

_CMD_TIMEOUT = 120

# GPT type aliases understood by the macOS 'gpt' tool
# (BSD gpt tool accepts the raw GUID hex string directly)


def _mb_to_sectors(mb: int) -> int:
    """Convert MiB to 512-byte sector count."""
    return mb * 2048


def commands(plan: PartitionPlan) -> list[list[str]]:
    """Build the ordered list of shell commands for the macOS runner.

    Sequence:
      1. diskutil unmountDisk (force-unmount all partitions)
      2. diskutil eraseDisk free None <disk>  (write blank GPT)
      3. gpt add -i N -b start -s size -t GUID <disk>  per partition
      4. newfs_msdos -F 32 for ESP slice

    Args:
        plan: Resolved partition plan.

    Returns:
        List of argv lists ready for subprocess.run().
    """
    disk_path = plan.disk.path
    cmds: list[list[str]] = []

    # Step 1: force-unmount everything on the disk
    cmds.append(["diskutil", "unmountDisk", "force", disk_path])

    # Step 2: erase disk and write a blank GPT
    cmds.append(["diskutil", "eraseDisk", "free", "None", disk_path])

    # Step 3: add GPT slices
    offset_mb = 1  # 1 MiB lead-in (GPT header)
    for part in plan.partitions:
        size_mb = part.size_mb or 0
        start_s = _mb_to_sectors(offset_mb)
        size_s = _mb_to_sectors(size_mb)
        cmds.append([
            "gpt", "add",
            "-i", str(part.index),
            "-b", str(start_s),
            "-s", str(size_s),
            "-t", part.type_guid.lower(),  # BSD gpt uses lowercase GUIDs
            disk_path,
        ])
        offset_mb += size_mb

    # Step 4: format ESP as FAT32 (only slice macOS can format natively)
    esp = _find_partition(plan, "fat32")
    if esp is not None:
        esp_path = f"{disk_path}s{esp.index}"  # macOS slice notation: disk2s1
        cmds.append(["newfs_msdos", "-F", "32", "-v", esp.label, esp_path])

    # NTFS: skipped — newfs_ntfs is not a standard macOS component.
    # The Windows partition is left with the correct GPT GUID (EBD0A0A2-...)
    # and will be formatted by the Windows installer or diskpart.

    # ext4 / swap: left unallocated — Ubuntu installer handles formatting.

    return cmds


def _find_partition(plan: PartitionPlan, fs: str) -> PlannedPartition | None:
    for part in plan.partitions:
        if part.fs == fs:
            return part
    return None


def apply(
    plan: PartitionPlan,
    *,
    dry_run: bool = False,
    on_progress: Callable[[str], None] | None = None,
) -> None:
    """Execute the macOS partition sequence for *plan*.

    Args:
        plan: Resolved partition plan (system-disk check must already be done).
        dry_run: If True, print commands but do not execute any subprocess.
        on_progress: Optional callback receiving human-readable status strings.

    Raises:
        RuntimeError: A subprocess step failed.
    """
    validate_disk_path(plan.disk.path)
    disk_id = plan.disk.id
    cmd_list = commands(plan)

    append_audit(
        "partition.apply.start",
        disk_id,
        "dry_run" if dry_run else "started",
        args={"dry_run": dry_run, "platform": "macos"},
    )

    def _emit(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    for cmd in cmd_list:
        cmd_str = " ".join(cmd)
        _emit(f"$ {cmd_str}")

        outcome: str
        error_msg: str | None = None

        if dry_run:
            outcome = "dry_run"
        else:
            try:
                result = subprocess.run(  # noqa: S603
                    cmd,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=_CMD_TIMEOUT,
                )
                if result.stdout:
                    _emit(result.stdout.rstrip())
                outcome = "success"
            except subprocess.CalledProcessError as exc:
                error_msg = exc.stderr or str(exc)
                outcome = "failure"
            except subprocess.TimeoutExpired:
                error_msg = f"Command timed out after {_CMD_TIMEOUT}s"
                outcome = "failure"

        append_audit(
            "partition.apply.command",
            disk_id,
            outcome,
            args={"cmd": cmd_str, "dry_run": dry_run},
            error=error_msg,
        )

        if outcome == "failure":
            msg = f"Partition step failed: {cmd_str}\n{error_msg}"
            append_audit("partition.apply.failure", disk_id, "failure", error=msg)
            raise RuntimeError(msg)

    final_outcome = "dry_run" if dry_run else "success"
    append_audit("partition.apply.success", disk_id, final_outcome)
    _emit("Partitioning complete.")
