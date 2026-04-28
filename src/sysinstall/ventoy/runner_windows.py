"""Windows Ventoy2Disk.exe subprocess wrapper.

Invokes: Ventoy2Disk.exe VTOYCLI /I /PhyDrive:N /GPT [/NOSB|/SecureBoot] [/R:MB]
Progress tracked by polling cli_percent.txt / cli_done.txt that Ventoy
writes into its working directory.
Timeout: 600s.
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

from sysinstall.ventoy.runner_windows_progress import poll_progress

log = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 600.0


def build_command(
    exe_path: Path,
    phy_drive_num: int,
    *,
    gpt: bool = True,
    secure_boot: bool = False,
    reserve_mb: int = 0,
) -> list[str]:
    """Build Ventoy2Disk.exe argument list (no subprocess side-effects)."""
    cmd: list[str] = [str(exe_path), "VTOYCLI", "/I", f"/PhyDrive:{phy_drive_num}"]
    if gpt:
        cmd.append("/GPT")
    if secure_boot:
        cmd.append("/SecureBoot")
    else:
        cmd.append("/NOSB")
    if reserve_mb > 0:
        cmd.append(f"/R:{reserve_mb}")
    return cmd


def _parse_phy_drive(device_path: str) -> int:
    r"""Extract physical drive number from e.g. '\\.\PhysicalDrive2' -> 2."""
    import re
    match = re.search(r"(\d+)$", device_path)
    if not match:
        raise ValueError(f"Cannot parse PhysicalDrive number from: {device_path!r}")
    return int(match.group(1))


def run_install(
    exe_path: Path,
    device_path: str,
    *,
    secure_boot: bool = False,
    reserve_mb: int = 0,
    on_progress: Callable[[int], None] | None = None,
) -> int:
    r"""Run Ventoy2Disk.exe against *device_path*, polling for progress.

    Args:
        exe_path: Path to Ventoy2Disk.exe extracted from the archive.
        device_path: Windows physical drive path, e.g. r'\\.\PhysicalDrive1'.
        secure_boot: Pass /SecureBoot flag (omits /NOSB).
        reserve_mb: Reserve trailing space in MB (/R: flag).
        on_progress: Called with progress percentage 0-100.

    Returns:
        0 on success, non-zero on failure.

    Raises:
        ValueError: device_path does not contain a numeric drive index.
        FileNotFoundError: exe_path does not exist.
        subprocess.TimeoutExpired: install exceeded 600s.
    """
    phy_num = _parse_phy_drive(device_path)
    cmd = build_command(
        exe_path,
        phy_num,
        secure_boot=secure_boot,
        reserve_mb=reserve_mb,
    )
    log.info("Running: %s", " ".join(cmd))

    # Ventoy writes progress files relative to its own working directory.
    with tempfile.TemporaryDirectory() as work_dir:
        work_path = Path(work_dir)
        percent_file = work_path / "cli_percent.txt"
        done_file = work_path / "cli_done.txt"

        proc = subprocess.Popen(  # noqa: S603
            cmd,
            cwd=work_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        def _read_percent() -> str | None:
            if percent_file.exists():
                return percent_file.read_text(encoding="utf-8", errors="replace")
            return None

        def _read_done() -> str | None:
            if done_file.exists():
                return done_file.read_text(encoding="utf-8", errors="replace")
            return None

        rc = poll_progress(
            _read_percent,
            _read_done,
            on_progress=on_progress,
            timeout=_TIMEOUT_SECONDS,
        )

        # Ensure the process is finished.
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

        log.info("Ventoy2Disk.exe exited; poll rc=%d, proc rc=%d", rc, proc.returncode)
        # Prefer the file-based result code (more reliable than process exit code).
        return rc if rc in (0, 1) else proc.returncode


def run_update(
    exe_path: Path,
    device_path: str,
    on_progress: Callable[[int], None] | None = None,
) -> int:
    """Run Ventoy2Disk.exe /U to update an existing Ventoy installation."""
    phy_num = _parse_phy_drive(device_path)
    cmd = [str(exe_path), "VTOYCLI", "/U", f"/PhyDrive:{phy_num}"]
    log.info("Running update: %s", " ".join(cmd))

    with tempfile.TemporaryDirectory() as work_dir:
        work_path = Path(work_dir)
        percent_file = work_path / "cli_percent.txt"
        done_file = work_path / "cli_done.txt"

        proc = subprocess.Popen(  # noqa: S603
            cmd,
            cwd=work_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        rc = poll_progress(
            lambda: percent_file.read_text(encoding="utf-8") if percent_file.exists() else None,
            lambda: done_file.read_text(encoding="utf-8") if done_file.exists() else None,
            on_progress=on_progress,
            timeout=_TIMEOUT_SECONDS,
        )

        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

        return rc if rc in (0, 1) else proc.returncode
