"""DualBootLayout dataclass with field-level validators.

GPT type GUIDs:
  ESP         C12A7328-F81F-11D2-BA4B-00A0C93EC93B
  MSR         E3C9E316-0B5C-4DB8-817D-F92DF00215AE
  Windows     EBD0A0A2-B9E5-4433-87C0-68B6B72699C7
  Linux root  0FC63DAF-8483-4772-8E79-3D69D8477DE4
  Linux swap  0657FD6D-A4AB-43C4-84E5-0933C84B4F4F
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# GPT type GUIDs (RFC 4122 format, uppercase)
# ---------------------------------------------------------------------------

GUID_ESP = "C12A7328-F81F-11D2-BA4B-00A0C93EC93B"
GUID_MSR = "E3C9E316-0B5C-4DB8-817D-F92DF00215AE"
GUID_WINDOWS = "EBD0A0A2-B9E5-4433-87C0-68B6B72699C7"
GUID_LINUX_FS = "0FC63DAF-8483-4772-8E79-3D69D8477DE4"
GUID_LINUX_SWAP = "0657FD6D-A4AB-43C4-84E5-0933C84B4F4F"

# Fixed overhead in MB (ESP + MSR)
_ESP_MB = 512
_MSR_MB = 16
_OVERHEAD_MB = _ESP_MB + _MSR_MB

_MIN_WINDOWS_GB = 30
_MAX_SWAP_GB = 32


class LayoutValidationError(ValueError):
    """Raised when the requested layout cannot fit or violates constraints."""


class LayoutTooLargeError(LayoutValidationError):
    """Total required space exceeds the disk capacity."""


@dataclass(frozen=True)
class DualBootLayout:
    """User-supplied sizing constraints for the dual-boot partition plan.

    Attributes:
        windows_size_gb: Windows NTFS partition size in GiB (must be >= 30).
        swap_size_gb: Linux swap size in GiB; 0 means no swap partition.
        disk_size_bytes: Total disk capacity used for validation only.
    """

    windows_size_gb: int
    swap_size_gb: int = field(default=4)
    disk_size_bytes: int = field(default=0)  # 0 = skip disk-size validation

    def __post_init__(self) -> None:
        self._validate()

    def _validate(self) -> None:
        if self.windows_size_gb < _MIN_WINDOWS_GB:
            raise LayoutValidationError(
                f"windows_size_gb={self.windows_size_gb} is below minimum {_MIN_WINDOWS_GB} GiB."
            )
        if not (0 <= self.swap_size_gb <= _MAX_SWAP_GB):
            raise LayoutValidationError(
                f"swap_size_gb={self.swap_size_gb} must be between 0 and {_MAX_SWAP_GB}."
            )
        if self.disk_size_bytes > 0:
            total_mb = self.total_required_mb
            disk_mb = self.disk_size_bytes // (1024 * 1024)
            if total_mb > disk_mb:
                raise LayoutTooLargeError(
                    f"Required {total_mb} MiB exceeds disk capacity {disk_mb} MiB "
                    f"(disk_size_bytes={self.disk_size_bytes})."
                )

    @property
    def total_required_mb(self) -> int:
        """Minimum total MB needed: overhead + Windows + 1 MiB for Linux root."""
        return (
            _OVERHEAD_MB
            + self.windows_size_gb * 1024
            + self.swap_size_gb * 1024
            + 1  # at least 1 MiB for Linux root
        )
