"""Public API for Ventoy installation and management.

Exports:
    install_to_disk  -- install Ventoy onto a target disk
    update           -- update an existing Ventoy installation
    is_installed     -- detect whether Ventoy is present on a disk
    UnsupportedHostError -- raised on macOS (Ventoy has no macOS support)

macOS note: Ventoy upstream has zero macOS support. Any call to install_to_disk
or update on darwin raises UnsupportedHostError immediately with instructions.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from pathlib import Path

from sysinstall.disks.base import Disk

log = logging.getLogger(__name__)

# URL shown in the macOS hard-fail message.
_MACOS_DD_DOCS_URL = (
    "https://www.ventoy.net/en/doc_start.html"
    " — use a Linux or Windows host, or flash a pre-built Ventoy image "
    "with: diskutil unmountDisk /dev/diskN && "
    "sudo dd if=ventoy.img of=/dev/diskN bs=1m"
)

MACOS_VENTOY_MESSAGE = (
    "USB creation via Ventoy is not supported on macOS. "
    "Ventoy upstream has no macOS CLI and no plans to add one.\n\n"
    "Alternatives:\n"
    "  1. Run 'sysinstall usb create' on a Linux or Windows host.\n"
    "  2. Flash a pre-built Ventoy disk image with dd:\n"
    f"     {_MACOS_DD_DOCS_URL}\n\n"
    "macOS is fully supported for disk listing and dual-boot finalization."
)


class UnsupportedHostError(RuntimeError):
    """Raised when Ventoy operations are requested on an unsupported OS (macOS)."""


def _require_supported_platform() -> None:
    """Raise UnsupportedHostError if running on macOS."""
    if sys.platform == "darwin":
        raise UnsupportedHostError(MACOS_VENTOY_MESSAGE)


def _extract_ventoy(archive_path: Path) -> Path:
    """Extract the Ventoy archive and return the actual top-level directory.

    Detects the archive's real top-level name (e.g. ``ventoy-1.1.05/``) instead
    of guessing from the archive filename — upstream zip names don't always
    match the inner folder (the Windows zip is ``ventoy-1.1.05-windows.zip``
    but unpacks to ``ventoy-1.1.05/``).
    """
    import tarfile
    import zipfile

    log.info("Extracting %s", archive_path)
    if archive_path.suffix == ".gz" or archive_path.name.endswith(".tar.gz"):
        with tarfile.open(archive_path, "r:gz") as tf:
            top_level = _archive_top_level([m.name for m in tf.getmembers()])
            extract_dir = archive_path.parent / top_level
            if not extract_dir.exists():
                tf.extractall(archive_path.parent)  # noqa: S202
    elif archive_path.suffix == ".zip":
        with zipfile.ZipFile(archive_path) as zf:
            top_level = _archive_top_level(zf.namelist())
            extract_dir = archive_path.parent / top_level
            if not extract_dir.exists():
                zf.extractall(archive_path.parent)
    else:
        raise RuntimeError(f"Unknown archive format: {archive_path}")

    log.debug("Ventoy extracted at %s", extract_dir)
    return extract_dir


def _archive_top_level(names: list[str]) -> str:
    """Return the single top-level directory name shared by all archive entries.

    Ventoy archives always pack a single root folder; if upstream ever ships
    a flat archive we fall back to the archive's own parent (caller handles).
    """
    tops = {n.split("/", 1)[0] for n in names if n and not n.startswith("/")}
    if len(tops) != 1:
        raise RuntimeError(
            f"Unexpected Ventoy archive layout — expected single top-level dir, got {tops!r}"
        )
    return tops.pop()


def _find_linux_script(extract_dir: Path) -> Path:
    """Locate Ventoy2Disk.sh within the extracted directory."""
    candidates = list(extract_dir.rglob("Ventoy2Disk.sh"))
    if not candidates:
        raise FileNotFoundError(f"Ventoy2Disk.sh not found under {extract_dir}")
    return candidates[0]


def _find_windows_exe(extract_dir: Path) -> Path:
    """Locate Ventoy2Disk.exe within the extracted directory."""
    candidates = list(extract_dir.rglob("Ventoy2Disk.exe"))
    if not candidates:
        raise FileNotFoundError(f"Ventoy2Disk.exe not found under {extract_dir}")
    return candidates[0]


def install_to_disk(
    disk: Disk,
    *,
    secure_boot: bool = False,
    reserve_mb: int = 0,
    dry_run: bool = False,
    on_progress: Callable[[int], None] | None = None,
) -> None:
    """Install Ventoy onto *disk*.

    Args:
        disk: Target disk (must not be system or fixed unless caller already
              passed safety guards).
        secure_boot: Enable Secure Boot support in Ventoy.
        reserve_mb: Reserve trailing space in MB.
        dry_run: Log commands without executing them. Audit entry gets
                 outcome="dry_run".
        on_progress: Callback receiving progress percentage 0-100.

    Raises:
        UnsupportedHostError: always on macOS.
        RuntimeError: Ventoy download, extraction, or install failed.
    """
    _require_supported_platform()

    from sysinstall.ventoy.downloader import fetch_ventoy

    if sys.platform == "win32":
        platform_key = "windows-x64"
    else:
        platform_key = "linux-x64"

    if dry_run:
        log.info(
            "[dry-run] Would download Ventoy (%s) and install to %s "
            "(secure_boot=%s, reserve_mb=%d)",
            platform_key,
            disk.path,
            secure_boot,
            reserve_mb,
        )
        return

    archive = fetch_ventoy(platform_key)
    extract_dir = _extract_ventoy(archive)

    if sys.platform == "win32":
        from sysinstall.ventoy.runner_windows import run_install as _win_install
        exe = _find_windows_exe(extract_dir)
        rc = _win_install(
            exe,
            disk.path,
            secure_boot=secure_boot,
            reserve_mb=reserve_mb,
            on_progress=on_progress,
        )
    else:
        from sysinstall.ventoy.mount import unmount_all_partitions
        from sysinstall.ventoy.runner_linux import run_install as _linux_install

        unmount_all_partitions(disk.path)
        script = _find_linux_script(extract_dir)
        rc = _linux_install(
            script,
            disk.path,
            secure_boot=secure_boot,
            reserve_mb=reserve_mb,
            on_progress=on_progress,
        )

    if rc != 0:
        raise RuntimeError(f"Ventoy install failed with return code {rc} on {disk.path}")

    # Write initial ventoy.json after successful install.
    _write_initial_config(disk.path)
    log.info("Ventoy installed successfully on %s", disk.path)


def _write_initial_config(device_path: str) -> None:
    """Mount first partition and write skeleton ventoy.json."""
    from sysinstall.ventoy.config import make_skeleton, write
    from sysinstall.ventoy.mount import mount_first_partition, unmount_partition

    try:
        mount_point = mount_first_partition(device_path)
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not mount first partition to write ventoy.json: %s", exc)
        return

    try:
        write(mount_point, make_skeleton())
        log.info("Wrote ventoy.json skeleton to %s", mount_point)
    finally:
        try:
            unmount_partition(str(mount_point))
        except Exception as exc:  # noqa: BLE001
            log.debug("Could not unmount %s: %s", mount_point, exc)


def update(disk: Disk) -> None:
    """Update an existing Ventoy installation on *disk*.

    Raises:
        UnsupportedHostError: always on macOS.
        RuntimeError: update failed.
    """
    _require_supported_platform()

    from sysinstall.ventoy.downloader import fetch_ventoy

    if sys.platform == "win32":
        platform_key = "windows-x64"
        archive = fetch_ventoy(platform_key)
        extract_dir = _extract_ventoy(archive)
        from sysinstall.ventoy.runner_windows import run_update as _win_update
        exe = _find_windows_exe(extract_dir)
        rc = _win_update(exe, disk.path)
    else:
        platform_key = "linux-x64"
        archive = fetch_ventoy(platform_key)
        extract_dir = _extract_ventoy(archive)
        from sysinstall.ventoy.runner_linux import run_update as _linux_update
        script = _find_linux_script(extract_dir)
        rc = _linux_update(script, disk.path)

    if rc != 0:
        raise RuntimeError(f"Ventoy update failed with return code {rc} on {disk.path}")
    log.info("Ventoy updated successfully on %s", disk.path)


def is_installed(disk: Disk) -> bool:
    """Return True if Ventoy appears to be installed on *disk*.

    Detection heuristic: check if any partition has a label "VTOYEFI" or
    "VENTOY", or if the first partition's filesystem matches Ventoy's layout.
    This is a best-effort check — no subprocess invoked.
    """
    ventoy_labels = {"VTOYEFI", "VENTOY", "ventoy", "vtoyefi"}
    for part in disk.partitions:
        if part.label and part.label.upper() in {lbl.upper() for lbl in ventoy_labels}:
            return True
    return False
