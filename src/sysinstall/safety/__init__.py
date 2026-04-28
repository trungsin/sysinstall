"""Safety module — disk operation gates, guards, prompts, and audit logging.

Public API
----------
check_destructive   -- unified gate pipeline (SystemDisk -> Encryption -> Fixed -> Mounted)
confirm_with_banner -- Rich red-banner confirm with countdown and rate-limit
SafetyError         -- typed exception from gate refusals
Gate                -- Protocol for gate classes
GateOptions         -- option bag passed through the pipeline
SystemDiskGate      -- hard-refuses system disk (no override)
EncryptionGate      -- refuses encrypted disks (--force-encrypted overrides)
FixedDiskGate       -- refuses non-removable disks (--allow-fixed-disk overrides)
MountedGate         -- refuses mounted disks (--auto-unmount overrides)
refuse_if_system    -- legacy guard (still used by guards.py callers)
refuse_if_fixed     -- legacy guard
confirm_destructive -- legacy guard
validate_disk_path  -- path allowlist guard
append_audit        -- write one JSONL audit entry
"""

from sysinstall.safety.audit import append_audit
from sysinstall.safety.errors import SafetyError
from sysinstall.safety.gates import (
    EncryptionGate,
    FixedDiskGate,
    Gate,
    GateOptions,
    MountedGate,
    SystemDiskGate,
    check_destructive,
)
from sysinstall.safety.guards import (
    confirm_destructive,
    refuse_if_fixed,
    refuse_if_system,
    validate_disk_path,
)
from sysinstall.safety.prompts import confirm_with_banner

__all__ = [
    # New unified API
    "check_destructive",
    "confirm_with_banner",
    "SafetyError",
    "Gate",
    "GateOptions",
    "SystemDiskGate",
    "EncryptionGate",
    "FixedDiskGate",
    "MountedGate",
    # Legacy guards — kept for backwards compatibility
    "refuse_if_system",
    "refuse_if_fixed",
    "confirm_destructive",
    "validate_disk_path",
    # Audit
    "append_audit",
]
