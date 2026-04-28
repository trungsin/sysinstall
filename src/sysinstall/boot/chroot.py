"""Chroot context manager for boot repair operations.

Sets up a full chroot environment with all necessary bind mounts:
  <tmpdir>/           <- Ubuntu root partition
  <tmpdir>/boot/efi/  <- EFI System Partition
  <tmpdir>/dev        <- bind from /dev
  <tmpdir>/dev/pts    <- bind from /dev/pts
  <tmpdir>/proc       <- bind from /proc
  <tmpdir>/sys        <- bind from /sys
  <tmpdir>/run        <- bind from /run

All mounts are tracked in a stack. __exit__ unmounts in reverse order.
Uses umount -l (lazy) as final fallback to prevent dangling mounts.
Cleanup always runs via try/finally.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import tempfile
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING

from sysinstall.safety.audit import append_audit

if TYPE_CHECKING:
    from sysinstall.disks.base import Partition

log = logging.getLogger(__name__)

# Bind-mount sources in the order they should be mounted.
# dev/pts must come after dev.
_BIND_SOURCES = ["/dev", "/dev/pts", "/proc", "/sys", "/run"]

# Timeout for mount/umount subprocess calls (seconds)
_MOUNT_TIMEOUT = 30


def _run_mount(args: list[str], *, timeout: int = _MOUNT_TIMEOUT) -> None:
    """Run a mount command. Raises RuntimeError on failure."""
    result = subprocess.run(
        args,
        capture_output=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace").strip()
        raise RuntimeError(f"mount failed ({' '.join(args)}): {stderr}")
    log.debug("mounted: %s", " ".join(args))


def _run_umount(target: str, *, lazy: bool = False) -> None:
    """Unmount target. Uses -l (lazy) if lazy=True. Logs but does not raise."""
    args = ["umount"]
    if lazy:
        args.append("-l")
    args.append(target)
    result = subprocess.run(args, capture_output=True, timeout=_MOUNT_TIMEOUT)
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace").strip()
        log.warning("umount%s failed for %s: %s", " -l" if lazy else "", target, stderr)
    else:
        log.debug("unmounted: %s", target)


class ChrootContext:
    """Context manager that sets up a chroot environment for grub-install.

    Usage::

        with ChrootContext(root_part, efi_part) as chroot_root:
            subprocess.run(["chroot", str(chroot_root), "grub-install", ...])

    Args:
        root_part: The Ubuntu root partition to mount as chroot root.
        efi_part: The EFI System Partition to mount at boot/efi.
                  Pass None for BIOS-mode repairs (no ESP needed).
        dry_run: If True, log intended mounts but skip actual subprocess calls.
    """

    def __init__(
        self,
        root_part: Partition,
        efi_part: Partition | None,
        *,
        dry_run: bool = False,
    ) -> None:
        self._root_part = root_part
        self._efi_part = efi_part
        self._dry_run = dry_run
        self._tmpdir: str | None = None
        # Stack of absolute paths that have been successfully mounted.
        # __exit__ unmounts in reverse order.
        self._mount_stack: list[str] = []

    def __enter__(self) -> Path:
        """Set up chroot mounts. Returns the chroot root Path."""
        if sys.platform != "linux" and not self._dry_run:
            raise RuntimeError("ChrootContext is only supported on Linux hosts.")
        if sys.platform != "linux":
            # dry_run on non-Linux: use a real tmpdir but skip all subprocess.
            pass

        self._tmpdir = tempfile.mkdtemp(prefix="sysinstall-chroot-")
        chroot_root = Path(self._tmpdir)
        log.info("chroot root: %s", chroot_root)

        try:
            self._mount_partition(self._root_part.id, str(chroot_root))

            if self._efi_part is not None:
                efi_target = str(chroot_root / "boot" / "efi")
                Path(efi_target).mkdir(parents=True, exist_ok=True)
                self._mount_partition(self._efi_part.id, efi_target)

            for src in _BIND_SOURCES:
                target = str(chroot_root / src.lstrip("/"))
                Path(target).mkdir(parents=True, exist_ok=True)
                self._mount_bind(src, target)

        except Exception:
            # Partial setup: unmount whatever was mounted before re-raising.
            self._unmount_all()
            raise

        return chroot_root

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Always unmount all mounts in reverse order."""
        self._unmount_all()

    def _mount_partition(self, dev_path: str, target: str) -> None:
        """Mount a partition at target and push target onto the mount stack."""
        append_audit(
            "boot.repair.command",
            target=dev_path,
            outcome="started" if not self._dry_run else "dry_run",
            args={"cmd": f"mount {dev_path} {target}"},
        )
        if not self._dry_run:
            _run_mount(["mount", dev_path, target])
        self._mount_stack.append(target)

    def _mount_bind(self, src: str, target: str) -> None:
        """Bind-mount src to target and push target onto the mount stack."""
        append_audit(
            "boot.repair.command",
            target=src,
            outcome="started" if not self._dry_run else "dry_run",
            args={"cmd": f"mount --bind {src} {target}"},
        )
        if not self._dry_run:
            _run_mount(["mount", "--bind", src, target])
        self._mount_stack.append(target)

    def _unmount_all(self) -> None:
        """Unmount everything in reverse mount order.

        In dry_run mode, skips all subprocess calls (nothing was actually mounted).
        """
        if not self._dry_run:
            # First pass: normal umount.
            for target in reversed(self._mount_stack):
                _run_umount(target)
            # Second pass: lazy fallback for any still-busy mounts.
            for target in reversed(self._mount_stack):
                _run_umount(target, lazy=True)

        self._mount_stack.clear()

        if self._tmpdir:
            try:
                Path(self._tmpdir).rmdir()
            except OSError as exc:
                log.warning("Could not remove chroot tmpdir %s: %s", self._tmpdir, exc)
