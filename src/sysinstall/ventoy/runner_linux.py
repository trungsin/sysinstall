"""Linux Ventoy2Disk.sh subprocess wrapper.

Invokes: sh Ventoy2Disk.sh -I -g [-s] [-r MB] /dev/sdX
Streams stdout to logger and fires on_progress(pct) for each percentage.
Timeout: 600s (large USBs are slow).
"""

from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable, Iterator
from pathlib import Path

from sysinstall.ventoy.runner_linux_progress import parse_progress

log = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 600


def build_command(
    script_path: Path,
    device_path: str,
    *,
    force: bool = True,
    gpt: bool = True,
    secure_boot: bool = False,
    reserve_mb: int = 0,
) -> list[str]:
    """Build the Ventoy2Disk.sh argument list (no subprocess side-effects)."""
    cmd: list[str] = ["sh", str(script_path)]
    cmd.append("-I" if force else "-i")
    if gpt:
        cmd.append("-g")
    if secure_boot:
        cmd.append("-s")
    if reserve_mb > 0:
        cmd.extend(["-r", str(reserve_mb)])
    cmd.append(device_path)
    return cmd


def run_install(
    script_path: Path,
    device_path: str,
    *,
    secure_boot: bool = False,
    reserve_mb: int = 0,
    on_progress: Callable[[int], None] | None = None,
) -> int:
    """Run Ventoy2Disk.sh against *device_path*, streaming output.

    Args:
        script_path: Absolute path to Ventoy2Disk.sh extracted from archive.
        device_path: Block device path, e.g. "/dev/sdb".
        secure_boot: Pass -s flag to enable Secure Boot support.
        reserve_mb: Reserve trailing space in MB (-r flag).
        on_progress: Called with progress percentage (0-100) as parsed from stdout.

    Returns:
        Process return code (0 = success).

    Raises:
        FileNotFoundError: script_path does not exist.
        subprocess.TimeoutExpired: install exceeded 600s.
    """
    cmd = build_command(
        script_path,
        device_path,
        secure_boot=secure_boot,
        reserve_mb=reserve_mb,
    )
    log.info("Running: %s", " ".join(cmd))

    proc = subprocess.Popen(  # noqa: S603
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,  # line-buffered
    )

    def _line_iter() -> Iterator[str]:
        assert proc.stdout is not None  # narrowing for mypy
        for line in proc.stdout:
            line = line.rstrip("\n")
            log.debug("[ventoy] %s", line)
            yield line

    parse_progress(_line_iter(), on_progress=on_progress)

    try:
        proc.wait(timeout=_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise

    log.info("Ventoy2Disk.sh exited with rc=%d", proc.returncode)
    return proc.returncode


def run_update(
    script_path: Path,
    device_path: str,
    on_progress: Callable[[int], None] | None = None,
) -> int:
    """Run Ventoy2Disk.sh -u to update an existing Ventoy installation."""
    cmd = ["sh", str(script_path), "-u", device_path]
    log.info("Running update: %s", " ".join(cmd))

    proc = subprocess.Popen(  # noqa: S603
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    def _line_iter() -> Iterator[str]:
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip("\n")
            log.debug("[ventoy] %s", line)
            yield line

    parse_progress(_line_iter(), on_progress=on_progress)

    try:
        proc.wait(timeout=_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise

    log.info("Ventoy2Disk.sh update exited with rc=%d", proc.returncode)
    return proc.returncode
