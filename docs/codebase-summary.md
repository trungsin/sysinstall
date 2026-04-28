# Codebase Summary

## Module Map
sysinstall follows a **CLI → Orchestrators → Backend Services** architecture:

```
src/sysinstall/
├── __init__.py                 # Package root, version constant
├── __main__.py                 # Entry point: python -m sysinstall
├── cli/                        # Typer CLI handlers (one file per command group)
│   ├── __init__.py
│   ├── disk.py                 # disk list, disk partition, disk list-efi
│   ├── usb.py                  # usb create, usb info
│   ├── iso.py                  # iso add, iso remove, iso list
│   └── boot.py                 # boot repair, boot detect, boot list
├── core/                       # Shared utilities
│   ├── __init__.py
│   ├── platform.py             # Detect host OS (returns "windows", "macos", "linux")
│   └── logging.py              # Centralized logger setup, audit log rotation
├── disks/                      # Disk enumeration & partition discovery
│   ├── __init__.py
│   ├── base.py                 # Abstract DiskEnumerator, Disk, Partition types
│   ├── identifiers.py          # Stable disk ID generation (serial-based)
│   ├── windows.py              # Windows disk enumeration (WMI, diskpart)
│   ├── macos.py                # macOS disk enumeration (diskutil, plistlib)
│   └── linux.py                # Linux disk enumeration (lsblk, sgdisk)
├── ventoy/                     # Ventoy USB creation & manifest management
│   ├── __init__.py
│   ├── manifest.py             # ventoy.json schema, parse/update logic
│   ├── installer.py            # Ventoy binary download, format USB
│   └── errors.py               # Ventoy-specific exceptions
├── partition/                  # Disk partitioning for dual-boot
│   ├── __init__.py
│   ├── planner.py              # Layout design (ESP, Windows, Linux, Swap)
│   ├── applier.py              # Apply partitions via sgdisk/diskpart
│   └── errors.py               # Partitioning exceptions
├── iso/                        # ISO image management
│   ├── __init__.py
│   ├── catalog.py              # ISO metadata, size verification
│   ├── copy.py                 # Copy ISO to Ventoy USB
│   ├── checksum.py             # SHA256 verification
│   ├── mount_resolver.py       # Detect ISO mount points
│   └── errors.py               # ISO-specific exceptions
├── boot/                       # Bootloader detection & repair
│   ├── __init__.py
│   ├── types.py                # EFI entry, GRUB config types
│   ├── detector.py             # Detect current EFI boot setup
│   ├── efi.py                  # EFI variable parsing (efibootmgr, nvram)
│   ├── grub.py                 # GRUB config parsing & generation
│   ├── backup.py               # ESP backup before repair
│   ├── chroot.py               # Mount + chroot helpers for live USB
│   ├── orchestrator.py         # Boot repair orchestration (calls backup, efi, grub)
│   └── errors.py               # Boot-related exceptions
└── safety/                     # Cross-cutting safety gates & logging
    ├── __init__.py
    ├── types.py                # Gate result types, audit log entry schema
    ├── guards.py               # System disk, encryption, fixed disk, mounted gates
    ├── prompts.py              # Interactive confirmation + dry-run rendering
    ├── audit.py                # Audit log writer + rotation
    └── errors.py               # Safety-specific exceptions
```

## Key Design Patterns

### 1. Platform Abstraction
Each OS-specific capability is isolated in its own module:
- **Interface** in `base.py` (abstract, e.g., `DiskEnumerator`)
- **Implementations** in `windows.py`, `macos.py`, `linux.py` (concrete classes)
- **Runtime dispatch** in CLI or orchestrators via `core.platform.get_platform()`

Example:
```python
# In cli/disk.py
from sysinstall.core.platform import get_platform
from sysinstall.disks.windows import WindowsDiskEnumerator
from sysinstall.disks.macos import MacOSDiskEnumerator
# ...
if get_platform() == "windows":
    enumerator = WindowsDiskEnumerator()
elif get_platform() == "macos":
    enumerator = MacOSDiskEnumerator()
disks = enumerator.list_disks()
```

### 2. Safety Gates (Cross-Cutting)
Before any destructive operation, `safety/guards.py` evaluates:
1. **SystemDiskGate:** Refuse if target is system/boot disk (NEVER overridable)
2. **EncryptionGate:** Refuse if disk encrypted (override: `--force-encrypted`)
3. **FixedDiskGate:** Refuse if disk not removable (override: `--allow-fixed-disk`)
4. **MountedGate:** Refuse if partitions mounted (override: `--auto-unmount`)

All refusals logged to audit trail with human-readable reason.

### 3. Orchestration Pattern
Complex workflows (e.g., dual-boot partitioning, boot repair) are handled by orchestrators:
- **`partition/orchestrator.py`** — Calls planner → applier → validation
- **`boot/orchestrator.py`** — Calls backup → efi-update → grub-restore → verify
- Orchestrators handle error recovery, logging, and rollback

### 4. Type Safety
All modules use Python type hints (compatible with `mypy --strict`):
```python
def list_disks(self) -> List[Disk]:
    ...

def partition_disk(self, device: str, layout: LayoutType) -> None:
    ...
```

## Critical Entry Points

### CLI (`src/sysinstall/cli/`)
- **`disk.py`** — List disks, partition for dual-boot, list EFI boot entries
- **`usb.py`** — Create Ventoy USB, show USB info
- **`iso.py`** — Add/remove/list ISOs on Ventoy USB
- **`boot.py`** — Detect boot setup, repair GRUB, list EFI entries

All CLI commands:
1. Parse user input + validate device IDs
2. Run safety gates (`safety/guards.py`)
3. Call appropriate backend module
4. Render output (human-readable or `--json`)
5. Log to audit trail

### Orchestration (`boot/orchestrator.py`, `partition/orchestrator.py`)
Handle multi-step workflows with error recovery:
- Validate inputs
- Create backups
- Apply changes
- Verify success
- Roll back on failure

## Test Organization

```
tests/
├── unit/                       # Mocked unit tests (≥80% coverage for core modules)
│   ├── test_disks_base.py
│   ├── test_disks_macos.py
│   ├── test_partition_planner.py
│   ├── test_iso_catalog.py
│   └── ...
├── integration/                # Integration tests (platform-conditional, ≥60%)
│   ├── test_disks_linux_lsblk.py
│   ├── test_boot_detector.py
│   └── ...
└── smoke/                      # VM smoke tests (Win11 + Ubuntu guests)
    └── vm-boot-repair.sh       # End-to-end boot repair sequence
```

## Dependencies & Imports

### Production Dependencies
- **`typer`** — CLI framework, command routing, help text
- **`rich`** — Colored output, progress bars, formatted tables
- **`psutil`** — Cross-platform disk and process utilities

### Standard Library (Heavily Used)
- **`subprocess`** — Shell out to diskpart, sgdisk, efibootmgr, etc.
- **`os`, `pathlib`** — File system operations
- **`json`** — Ventoy manifest parsing
- **`logging`** — Audit trail + debug logs
- **`platform`, `sys`** — Host OS detection

### No External Build Tools
- No compiled C extensions (pure Python)
- pyinstaller handles bundling on each platform

## Version & Metadata
- **Current version:** `0.0.1` (set in `__init__.py` and `pyproject.toml`)
- **Target Python:** 3.12+ (enforced in `pyproject.toml`)
- **Binary packaging:** PyInstaller per-platform (see `sysinstall.spec`)

## Common Code Paths

### "User wants to create dual-boot"
1. `cli/disk.py:partition()` → validates device ID
2. Safety gates check system disk, encryption, mounted partitions
3. `partition/orchestrator.py` → calls planner → applier
4. Audit log records partition changes
5. User installs Windows, then Ubuntu
6. User runs `cli/boot.py:repair()` from Ubuntu live USB
7. `boot/orchestrator.py` → backup ESP → detect current GRUB → restore boot entries → verify

### "User wants to create Ventoy USB"
1. `cli/usb.py:create()` → validates device ID
2. Safety gates check system disk, mounted partitions
3. `ventoy/installer.py` → download Ventoy binary
4. Format USB with Ventoy bootloader
5. Create `ventoy.json` manifest
6. Audit log records USB creation

## Limitations & Gaps
- **macOS cannot create Ventoy USB** (upstream limitation; document workaround in `install/macos.md`)
- **No persistence file UI** (Ventoy `.dat` deferred to v2)
- **No GUI** (CLI only)
- **No BIOS-mode dual-boot** (UEFI only)

See `project-overview-pdr.md` for full non-goals list.
