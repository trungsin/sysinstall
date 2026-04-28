"""Safety gate pipeline: SystemDiskGate, EncryptionGate, FixedDiskGate, MountedGate.

Each gate implements the Gate protocol: check(disk, op, opts) -> None or raises SafetyError.
The check_destructive() pipeline runs all four gates in order. Every gate decision
(pass or refuse) is recorded in the audit log.

Architecture:
  - Gate classes are pure; subprocess detection helpers are module-level functions.
  - encryption/mount detection lives here ONLY; partition.preflight shims re-export.
  - System-disk gate has NO override — explicitly tested.
"""

from __future__ import annotations

import subprocess
import sys
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from sysinstall.disks.base import Disk
from sysinstall.safety.errors import SafetyError

if TYPE_CHECKING:
    pass

_CMD_TIMEOUT = 30


# ---------------------------------------------------------------------------
# Gate protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class Gate(Protocol):
    """Protocol all safety gates must satisfy."""

    def check(self, disk: Disk, op: str, opts: GateOptions) -> None:
        """Check the gate condition. Raises SafetyError on refusal.

        Args:
            disk: Target disk being operated on.
            op: Short operation name, e.g. "usb_create".
            opts: Resolved option flags controlling override behaviour.
        """
        ...  # pragma: no cover


class GateOptions:
    """Resolved flags passed down the gate pipeline.

    All fields default to False (most restrictive). CLI layers set these
    from per-subcommand flags and/or global Typer context flags.
    """

    __slots__ = ("allow_fixed", "force_encrypted", "auto_unmount", "confirmed", "dry_run")

    def __init__(
        self,
        *,
        allow_fixed: bool = False,
        force_encrypted: bool = False,
        auto_unmount: bool = False,
        confirmed: bool = False,
        dry_run: bool = False,
    ) -> None:
        self.allow_fixed = allow_fixed
        self.force_encrypted = force_encrypted
        self.auto_unmount = auto_unmount
        self.confirmed = confirmed
        self.dry_run = dry_run


# ---------------------------------------------------------------------------
# Audit helper (avoid circular import with full audit module)
# ---------------------------------------------------------------------------


def _audit_gate(gate_name: str, outcome: str, disk_id: str, op: str) -> None:
    """Record a single gate decision to the JSONL audit log (best-effort)."""
    try:
        from sysinstall.safety.audit import append_audit

        append_audit(
            action="safety_gate",
            target=disk_id,
            outcome=outcome,
            args={"gate": gate_name, "op": op},
        )
    except Exception:  # noqa: BLE001
        # Audit failure must never abort the gate pipeline.
        pass


# ---------------------------------------------------------------------------
# Gate 1: SystemDiskGate — NEVER overridable
# ---------------------------------------------------------------------------


class SystemDiskGate:
    """Refuses any operation on the running OS disk. No override exists."""

    def check(self, disk: Disk, op: str, opts: GateOptions) -> None:
        """Raise SafetyError(category='system_disk') if disk.is_system.

        This gate ignores all opts flags — it is unconditional.
        """
        if disk.is_system:
            _audit_gate("system_disk", "refuse", disk.id, op)
            raise SafetyError(
                f"Refusing {op!r} on system disk {disk.path!r} "
                f"(model={disk.model!r}, id={disk.id!r}). "
                "This disk contains the running OS. No override flag exists.",
                category="system_disk",
                overridable=False,
                suggestion=(
                    "Use a different disk. If this is a false positive, "
                    "report a bug — there is no workaround by design."
                ),
                disk_id=disk.id,
                op=op,
            )
        _audit_gate("system_disk", "pass", disk.id, op)


# ---------------------------------------------------------------------------
# Encryption detection helpers (canonical implementation — preflight shims these)
# ---------------------------------------------------------------------------


def _detect_encryption_linux(disk: Disk) -> str:
    """Return 'full', 'partial', 'none', or 'unknown' for LUKS on Linux."""
    if not disk.partitions:
        return "none"
    if not _tool_available("cryptsetup"):
        return "unknown"
    encrypted = 0
    for part in disk.partitions:
        try:
            ret = subprocess.run(  # noqa: S603
                ["cryptsetup", "isLuks", part.id],
                capture_output=True,
                timeout=_CMD_TIMEOUT,
            )
            if ret.returncode == 0:
                encrypted += 1
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return "unknown"
    if encrypted == 0:
        return "none"
    return "full" if encrypted == len(disk.partitions) else "partial"


def _detect_encryption_macos(disk: Disk) -> str:
    """Return 'full', 'partial', 'none', or 'unknown' for FileVault/APFS on macOS."""
    try:
        result = subprocess.run(  # noqa: S603
            ["fdesetup", "status"],
            capture_output=True,
            text=True,
            timeout=_CMD_TIMEOUT,
        )
        if "on" in result.stdout.lower():
            return "full"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return "unknown"
    # Check APFS encrypted volumes heuristically
    try:
        result = subprocess.run(  # noqa: S603
            ["diskutil", "apfs", "list", "-plist"],
            capture_output=True,
            text=True,
            timeout=_CMD_TIMEOUT,
        )
        if disk.path in result.stdout and "encrypted" in result.stdout.lower():
            return "partial"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return "none"


def _detect_encryption_windows(disk: Disk) -> str:  # noqa: ARG001
    """Return 'full', 'partial', 'none', or 'unknown' for BitLocker on Windows."""
    try:
        result = subprocess.run(  # noqa: S603
            [
                "powershell.exe",
                "-NonInteractive",
                "-Command",
                "Get-BitLockerVolume | Select-Object -ExpandProperty ProtectionStatus",
            ],
            capture_output=True,
            text=True,
            timeout=_CMD_TIMEOUT,
        )
        lines = [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]
        if not lines:
            return "none"
        on_count = sum(1 for ln in lines if ln.lower() == "on")
        if on_count == 0:
            return "none"
        return "full" if on_count == len(lines) else "partial"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return "unknown"


def detect_encryption(disk: Disk) -> str:
    """Canonical encryption detection for disk. Returns 'full'|'partial'|'none'|'unknown'.

    This is the single source of truth; partition.preflight re-exports from here.
    """
    if sys.platform == "linux":
        return _detect_encryption_linux(disk)
    if sys.platform == "darwin":
        return _detect_encryption_macos(disk)
    if sys.platform == "win32":
        return _detect_encryption_windows(disk)
    return "unknown"


# ---------------------------------------------------------------------------
# Gate 2: EncryptionGate — overridable with force_encrypted
# ---------------------------------------------------------------------------


class EncryptionGate:
    """Refuses operations on encrypted disks unless force_encrypted is set."""

    def check(self, disk: Disk, op: str, opts: GateOptions) -> None:
        """Raise SafetyError(category='encrypted') for encrypted disks.

        With opts.force_encrypted=True, logs a warning but does not refuse.
        """
        status = detect_encryption(disk)
        if status in ("full", "partial"):
            if opts.force_encrypted:
                # Warn-only per architecture decision #7
                _audit_gate("encryption", "pass_forced", disk.id, op)
                return
            _audit_gate("encryption", "refuse", disk.id, op)
            raise SafetyError(
                f"Disk {disk.path!r} (id={disk.id!r}) appears encrypted ({status}). "
                f"Proceeding with {op!r} may destroy encrypted data or the recovery key.",
                category="encrypted",
                overridable=True,
                suggestion="Pass --force-encrypted to override (data loss risk).",
                disk_id=disk.id,
                op=op,
            )
        _audit_gate("encryption", "pass", disk.id, op)


# ---------------------------------------------------------------------------
# Gate 3: FixedDiskGate — overridable with allow_fixed
# ---------------------------------------------------------------------------


class FixedDiskGate:
    """Refuses operations on non-removable disks unless allow_fixed is set."""

    def check(self, disk: Disk, op: str, opts: GateOptions) -> None:
        """Raise SafetyError(category='fixed_disk') for fixed disks.

        With opts.allow_fixed=True, the check is skipped.
        """
        if not disk.is_removable and not opts.allow_fixed:
            _audit_gate("fixed_disk", "refuse", disk.id, op)
            raise SafetyError(
                f"Disk {disk.path!r} (id={disk.id!r}) is not removable. "
                f"Operation {op!r} typically targets USB/removable media only.",
                category="fixed_disk",
                overridable=True,
                suggestion="Pass --allow-fixed-disk to override (use with extreme caution).",
                disk_id=disk.id,
                op=op,
            )
        _audit_gate("fixed_disk", "pass", disk.id, op)


# ---------------------------------------------------------------------------
# Mount detection and unmounting (canonical — preflight shims these)
# ---------------------------------------------------------------------------


def _mounted_partitions(disk: Disk) -> list[tuple[str, str]]:
    """Return list of (partition_id, mountpoint) pairs for all mounted partitions."""
    result = []
    for part in disk.partitions:
        for mp in part.mountpoints:
            if mp:
                result.append((part.id, mp))
    return result


def unmount_all(disk: Disk) -> list[str]:
    """Best-effort unmount of all mounted partitions on disk.

    Returns list of warning strings for any unmount that failed (non-fatal).
    This is the canonical implementation; partition.preflight re-exports from here.
    """
    if sys.platform == "linux":
        return _unmount_linux(disk)
    if sys.platform == "darwin":
        return _unmount_macos(disk)
    if sys.platform == "win32":
        return _unmount_windows(disk)
    return []


def _unmount_linux(disk: Disk) -> list[str]:
    warnings: list[str] = []
    for part in disk.partitions:
        for mp in part.mountpoints:
            try:
                subprocess.run(  # noqa: S603
                    ["umount", mp],
                    capture_output=True,
                    timeout=_CMD_TIMEOUT,
                )
            except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
                warnings.append(f"Could not unmount {mp}: {exc}")
    return warnings


def _unmount_macos(disk: Disk) -> list[str]:
    warnings: list[str] = []
    try:
        subprocess.run(  # noqa: S603
            ["diskutil", "unmountDisk", "force", disk.path],
            capture_output=True,
            timeout=_CMD_TIMEOUT,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        warnings.append(f"diskutil unmountDisk failed for {disk.path}: {exc}")
    return warnings


def _unmount_windows(disk: Disk) -> list[str]:
    warnings: list[str] = []
    try:
        disk_num = int(disk.path.replace("\\\\.\\PhysicalDrive", ""))
        script = (
            f"Get-Partition -DiskNumber {disk_num} | "
            "ForEach-Object { $_ | Remove-PartitionAccessPath "
            "-AccessPath ($_.AccessPaths | Select-Object -First 1) "
            "-ErrorAction SilentlyContinue }"
        )
        subprocess.run(  # noqa: S603
            ["powershell.exe", "-NonInteractive", "-Command", script],
            capture_output=True,
            timeout=_CMD_TIMEOUT,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError) as exc:
        warnings.append(f"Could not dismount partitions on {disk.path}: {exc}")
    return warnings


# ---------------------------------------------------------------------------
# Gate 4: MountedGate — auto-unmount or prompt
# ---------------------------------------------------------------------------


class MountedGate:
    """Refuses operations on disks with mounted partitions (or auto-unmounts)."""

    def check(self, disk: Disk, op: str, opts: GateOptions) -> None:
        """Raise SafetyError(category='mounted') if any partition is mounted.

        With opts.auto_unmount=True, attempts unmount first; raises only if
        unmount fails.
        """
        mounted = _mounted_partitions(disk)
        if not mounted:
            _audit_gate("mounted", "pass", disk.id, op)
            return

        if opts.auto_unmount:
            warnings = unmount_all(disk)
            # Re-check after unmount attempt
            still_mounted = _mounted_partitions(disk)
            if not still_mounted:
                _audit_gate("mounted", "pass_auto_unmount", disk.id, op)
                if warnings:
                    import logging
                    logging.getLogger(__name__).warning(
                        "Unmount warnings: %s", "; ".join(warnings)
                    )
                return
            # Unmount failed — fall through to refuse
            _audit_gate("mounted", "refuse", disk.id, op)
            raise SafetyError(
                f"Disk {disk.path!r} still has mounted partitions after unmount attempt: "
                + ", ".join(f"{pid}@{mp}" for pid, mp in still_mounted),
                category="mounted",
                overridable=True,
                suggestion="Manually unmount all partitions and retry.",
                disk_id=disk.id,
                op=op,
            )

        _audit_gate("mounted", "refuse", disk.id, op)
        mount_summary = ", ".join(f"{pid}@{mp}" for pid, mp in mounted)
        raise SafetyError(
            f"Disk {disk.path!r} has mounted partitions: {mount_summary}. "
            f"Proceeding with {op!r} while partitions are mounted risks data corruption.",
            category="mounted",
            overridable=True,
            suggestion="Pass --auto-unmount to unmount automatically, or unmount manually.",
            disk_id=disk.id,
            op=op,
        )


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _tool_available(name: str) -> bool:
    """Return True if name resolves to an executable on PATH."""
    try:
        subprocess.run(  # noqa: S603
            ["which", name],
            capture_output=True,
            timeout=5,
        )
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


# ---------------------------------------------------------------------------
# Canonical pipeline
# ---------------------------------------------------------------------------

# Ordered gate instances — SystemDiskGate is always first and never skipped.
_GATES: list[Any] = [SystemDiskGate(), EncryptionGate(), FixedDiskGate(), MountedGate()]


def check_destructive(
    disk: Disk,
    op: str,
    *,
    allow_fixed: bool = False,
    force_encrypted: bool = False,
    auto_unmount: bool = False,
    confirmed: bool = False,
    dry_run: bool = False,
) -> None:
    """Run all safety gates for a destructive disk operation.

    Gates run in order: SystemDisk -> Encryption -> FixedDisk -> Mounted.
    SystemDiskGate is NEVER skipped regardless of any flag combination.

    Args:
        disk: Target disk.
        op: Short operation name for audit log and error messages.
        allow_fixed: Skip FixedDiskGate (--allow-fixed-disk).
        force_encrypted: Warn-only on EncryptionGate (--force-encrypted).
        auto_unmount: Auto-unmount in MountedGate (--auto-unmount).
        confirmed: Whether user already confirmed (passed to prompt layer).
        dry_run: Dry-run mode flag (passed through for audit context).

    Raises:
        SafetyError: on gate refusal with category/overridable/suggestion.
    """
    opts = GateOptions(
        allow_fixed=allow_fixed,
        force_encrypted=force_encrypted,
        auto_unmount=auto_unmount,
        confirmed=confirmed,
        dry_run=dry_run,
    )

    for gate in _GATES:
        # FixedDiskGate: skip when allow_fixed set
        if isinstance(gate, FixedDiskGate) and opts.allow_fixed:
            _audit_gate("fixed_disk", "skipped", disk.id, op)
            continue
        # EncryptionGate: allow pass-through with force_encrypted
        # (gate itself handles this case, but we still call it for audit)
        gate.check(disk, op, opts)

    # All gates passed — log overall pass
    try:
        from sysinstall.safety.audit import append_audit
        append_audit(
            action="safety_check_destructive",
            target=disk.id,
            outcome="dry_run" if dry_run else "pass",
            args={"op": op, "allow_fixed": allow_fixed, "force_encrypted": force_encrypted},
        )
    except Exception:  # noqa: BLE001
        pass
