"""Windows partition runner — builds and executes a PowerShell script.

Command builder (commands()) is pure — no subprocess; fully unit-testable.
Executor (apply()) runs the script via powershell.exe.

Windows limitations vs Linux runner:
  - ext4 and swap are not supported on Windows. Partitions 4 and 5 are
    created with the correct GPT type GUIDs but left unformatted
    (New-Partition without Format-Volume). The Ubuntu installer will
    detect and format them.
  - MSR partition is created via New-Partition with the MSR GUID; Windows
    manages it automatically.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable

from sysinstall.partition.planner import PartitionPlan
from sysinstall.safety.audit import append_audit

_PS_TIMEOUT = 600
_MB = 1024 * 1024


def commands(plan: PartitionPlan) -> list[str]:
    """Build the PowerShell script lines for the Windows runner.

    Returns a list of PowerShell statement strings (not argv lists).
    The apply() function joins them into a single -Command argument.

    Sequence:
      1. Clear-Disk -Number N -RemoveData -Confirm:$false
      2. Initialize-Disk -Number N -PartitionStyle GPT
      3. New-Partition per slice with -GptType GUID and -Size bytes
      4. Add-PartitionAccessPath for ESP (mount as drive letter)
      5. Format-Volume for ESP (FAT32) and Windows (NTFS)

    Args:
        plan: Resolved partition plan.

    Returns:
        List of PowerShell statement strings.
    """
    # Extract physical disk number from path \\.\PhysicalDriveN
    disk_num = _extract_disk_number(plan.disk.path)
    lines: list[str] = []

    lines.append(f"Clear-Disk -Number {disk_num} -RemoveData -Confirm:$false")
    lines.append(f"Initialize-Disk -Number {disk_num} -PartitionStyle GPT")

    for part in plan.partitions:
        size_bytes = (part.size_mb or 0) * _MB
        guid = part.type_guid.upper()
        size_arg = f"-Size {size_bytes}"
        lines.append(
            f"New-Partition -DiskNumber {disk_num} "
            f"-GptType '{{{guid}}}' "
            f"{size_arg}"
        )

    # Format ESP as FAT32
    esp_index = _find_index(plan, "fat32")
    if esp_index is not None:
        lines.append(
            f"Get-Partition -DiskNumber {disk_num} -PartitionNumber {esp_index} "
            f"| Format-Volume -FileSystem FAT32 -NewFileSystemLabel EFI -Confirm:$false"
        )

    # Format Windows partition as NTFS
    win_index = _find_index(plan, "ntfs")
    if win_index is not None:
        lines.append(
            f"Get-Partition -DiskNumber {disk_num} -PartitionNumber {win_index} "
            f"| Format-Volume -FileSystem NTFS -NewFileSystemLabel Windows -Confirm:$false"
        )

    # ext4 and swap partitions are intentionally left unformatted.
    # New-Partition above creates them with the correct GPT GUIDs.
    # The Ubuntu installer will detect and format them.

    return lines


def _extract_disk_number(path: str) -> int:
    r"""Extract integer disk number from \\.\PhysicalDriveN."""
    prefix = r"\\.\PhysicalDrive"
    if path.startswith(prefix):
        try:
            return int(path[len(prefix):])
        except ValueError:
            pass
    raise ValueError(f"Cannot extract disk number from path: {path!r}")


def _find_index(plan: PartitionPlan, fs: str) -> int | None:
    for part in plan.partitions:
        if part.fs == fs:
            return part.index
    return None


def apply(
    plan: PartitionPlan,
    *,
    dry_run: bool = False,
    on_progress: Callable[[str], None] | None = None,
) -> None:
    """Execute the Windows partition sequence for *plan*.

    Args:
        plan: Resolved partition plan (system-disk check must already be done).
        dry_run: If True, print script but do not execute any subprocess.
        on_progress: Optional callback receiving human-readable status strings.

    Raises:
        RuntimeError: PowerShell execution failed.
    """
    disk_id = plan.disk.id
    script_lines = commands(plan)
    script = "; ".join(script_lines)

    append_audit(
        "partition.apply.start",
        disk_id,
        "dry_run" if dry_run else "started",
        args={"dry_run": dry_run, "platform": "windows"},
    )

    def _emit(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    for line in script_lines:
        _emit(f"PS> {line}")

    outcome: str
    error_msg: str | None = None

    if dry_run:
        outcome = "dry_run"
    else:
        cmd = ["powershell.exe", "-NonInteractive", "-Command", script]
        try:
            result = subprocess.run(  # noqa: S603
                cmd,
                check=True,
                capture_output=True,
                text=True,
                timeout=_PS_TIMEOUT,
            )
            if result.stdout:
                _emit(result.stdout.rstrip())
            outcome = "success"
        except subprocess.CalledProcessError as exc:
            error_msg = exc.stderr or str(exc)
            outcome = "failure"
        except subprocess.TimeoutExpired:
            error_msg = f"PowerShell timed out after {_PS_TIMEOUT}s"
            outcome = "failure"

    append_audit(
        "partition.apply.command",
        disk_id,
        outcome,
        args={"cmd": "powershell.exe", "dry_run": dry_run},
        error=error_msg,
    )

    if outcome == "failure":
        msg = f"Windows partition script failed.\n{error_msg}"
        append_audit("partition.apply.failure", disk_id, "failure", error=msg)
        raise RuntimeError(msg)

    final_outcome = "dry_run" if dry_run else "success"
    append_audit("partition.apply.success", disk_id, final_outcome)
    _emit("Partitioning complete.")
