"""Linux partition runner — builds and executes sgdisk + mkfs command sequences.

Command builder (commands()) is pure — no subprocess; fully unit-testable.
Executor (apply()) runs the list and streams progress via on_progress callback.

Disk must be pre-validated (system-disk check, path validation) by the caller
before any function here is invoked.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable

from sysinstall.partition.planner import PartitionPlan, PlannedPartition
from sysinstall.safety.audit import append_audit
from sysinstall.safety.guards import validate_disk_path

_SGDISK_TIMEOUT = 60
_MKFS_TIMEOUT = 600


def _sector_range(start_mb: int, size_mb: int) -> tuple[str, str]:
    """Convert MiB offsets to sgdisk sector notation (2048-sector = 1 MiB alignment)."""
    sectors_per_mb = 2048  # 512-byte sectors, 1 MiB = 2048 sectors
    start = start_mb * sectors_per_mb
    end = (start_mb + size_mb) * sectors_per_mb - 1
    return str(start), str(end)


def commands(plan: PartitionPlan) -> list[list[str]]:
    """Build the ordered list of shell commands for the Linux runner.

    Returns a list of argv lists (no shell=True). Includes:
      1. sgdisk -Z (zap) + partition creation args in one invocation.
      2. Per-filesystem mkfs.* or mkswap commands.
      3. partprobe + udevadm settle postlude.

    Args:
        plan: Resolved partition plan.

    Returns:
        List of argv lists ready to pass to subprocess.run().
    """
    disk_path = plan.disk.path
    cmds: list[list[str]] = []

    # --- sgdisk: zap + create all partitions in one call ---
    sgdisk_args: list[str] = ["sgdisk", "--zap-all"]
    offset_mb = 1  # 1 MiB lead-in for alignment

    for part in plan.partitions:
        size_mb = part.size_mb or 0
        start_s, end_s = _sector_range(offset_mb, size_mb)
        n = str(part.index)
        sgdisk_args += [
            f"--new={n}:{start_s}:{end_s}",
            f"--typecode={n}:{part.type_guid}",
            f"--change-name={n}:{part.label}",
        ]
        offset_mb += size_mb

    sgdisk_args.append(disk_path)
    cmds.append(sgdisk_args)

    # --- mkfs per partition ---
    for part in plan.partitions:
        part_path = _part_path(disk_path, part.index)
        mkfs_cmd = _mkfs_command(part, part_path)
        if mkfs_cmd:
            cmds.append(mkfs_cmd)

    # --- postlude: inform kernel + wait for udev ---
    cmds.append(["partprobe", disk_path])
    cmds.append(["udevadm", "settle"])

    return cmds


def _part_path(disk_path: str, index: int) -> str:
    """Return partition device path for a given disk path and partition index."""
    # NVMe disks use 'p' separator: /dev/nvme0n1 -> /dev/nvme0n1p1
    if "nvme" in disk_path:
        return f"{disk_path}p{index}"
    return f"{disk_path}{index}"


def _mkfs_command(part: PlannedPartition, part_path: str) -> list[str] | None:
    """Return the mkfs argv for a partition, or None if no formatting needed."""
    if part.fs == "fat32":
        return ["mkfs.fat", "-F", "32", "-n", part.label, part_path]
    if part.fs == "ntfs":
        # -Q = quick format; -L = volume label
        return ["mkfs.ntfs", "-Q", "-L", part.label, part_path]
    if part.fs == "ext4":
        return ["mkfs.ext4", "-L", part.label, part_path]
    if part.fs == "swap":
        return ["mkswap", "-L", part.label, part_path]
    # unallocated / MSR: no filesystem
    return None


def apply(
    plan: PartitionPlan,
    *,
    dry_run: bool = False,
    on_progress: Callable[[str], None] | None = None,
) -> None:
    """Execute the Linux partition sequence for *plan*.

    Args:
        plan: Resolved partition plan (system-disk check must already be done).
        dry_run: If True, print commands but do not execute any subprocess.
        on_progress: Optional callback receiving human-readable status strings.

    Raises:
        RuntimeError: A subprocess step failed. Disk is left in post-zap state.
    """
    validate_disk_path(plan.disk.path)
    disk_id = plan.disk.id
    cmd_list = commands(plan)

    append_audit(
        "partition.apply.start",
        disk_id,
        "dry_run" if dry_run else "started",
        args={"dry_run": dry_run, "partitions": len(plan.partitions)},
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
            timeout = _SGDISK_TIMEOUT if cmd[0] == "sgdisk" else _MKFS_TIMEOUT
            try:
                result = subprocess.run(  # noqa: S603
                    cmd,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                if result.stdout:
                    _emit(result.stdout.rstrip())
                outcome = "success"
            except subprocess.CalledProcessError as exc:
                error_msg = exc.stderr or str(exc)
                outcome = "failure"
            except subprocess.TimeoutExpired:
                error_msg = f"Command timed out after {timeout}s: {cmd_str}"
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
