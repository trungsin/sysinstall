# Phase 02 — Cross-Platform Disk Enumeration

**Status**: pending
**Effort**: 2d
**Owner**: TBD

## Context Links
- Plan: [../plan.md](./plan.md)
- Research: `research/researcher-02-disk-enumeration.md`, `-03`, `-04`, `-05`

## Overview
Build the unified disk abstraction. Foundation for every destructive command — `disk list`, `usb create`, `disk partition`, `boot repair` all consume it. Three platform backends behind one interface.

## Key Insights
- `psutil` covers mounted FS but NOT raw block devices → must shell out per platform.
- Stable disk ID = `bus + serial` (NOT drive letter / `/dev/sdX` path which can shift).
- System-disk detection logic differs per platform but unified flag (`is_system: bool`) suffices for safety layer.

## Requirements
### Functional
- `list_disks() -> list[Disk]` — enumerate all physical disks on host.
- `get_disk(disk_id) -> Disk` — re-resolve by stable ID.
- `Disk.is_system` correctly true for boot drive on all 3 platforms.
- `sysinstall disk list` CLI: shows `id | size | model | bus | system`.
- `sysinstall disk show <id>` — detailed view incl. partitions.
- JSON output mode (`--json`) for scripting.

### Non-Functional
- Enumeration <2s on systems with 5 disks.
- Zero crashes if `diskutil`/`lsblk`/PowerShell missing — clear error.
- No raw-disk reads (enumeration unprivileged).

## Architecture

```python
# src/sysinstall/disks/base.py
@dataclass(frozen=True)
class Partition:
    id: str
    fs_type: str | None
    size_bytes: int
    mountpoints: tuple[str, ...]
    label: str | None

@dataclass(frozen=True)
class Disk:
    id: str                       # stable: e.g. "usb:Kingston:5B860..."
    path: str                     # current device path (/dev/disk2, \\.\PhysicalDrive2, etc.)
    size_bytes: int
    model: str
    serial: str | None
    bus: Literal["usb","sata","nvme","scsi","unknown"]
    is_removable: bool
    is_system: bool
    partitions: tuple[Partition, ...]

class DiskBackend(Protocol):
    def list_disks(self) -> list[Disk]: ...
    def get_disk(self, disk_id: str) -> Disk: ...
```

```
src/sysinstall/disks/
├── __init__.py              # backend selector + public API
├── base.py                  # dataclasses + Protocol
├── identifiers.py           # stable-ID derivation
├── macos.py                 # diskutil list -plist
├── linux.py                 # lsblk -J -O
└── windows.py               # PowerShell Get-Disk/Get-Partition
```

Selector at import:
```python
def _backend() -> DiskBackend:
    if sys.platform == "darwin": return MacOSBackend()
    if sys.platform == "win32":  return WindowsBackend()
    return LinuxBackend()
```

## Related Code Files
**Create**:
- `src/sysinstall/disks/{__init__.py,base.py,identifiers.py,macos.py,linux.py,windows.py}`
- `src/sysinstall/cli/disk.py` (replace stub with `list`, `show` commands)
- `tests/disks/test_macos_parser.py`
- `tests/disks/test_linux_parser.py`
- `tests/disks/test_windows_parser.py`
- `tests/disks/fixtures/{diskutil-plist.xml,lsblk.json,powershell-disk.json}`

**Modify**:
- `src/sysinstall/cli/__init__.py` — wire disk subcommands.

## Implementation Steps

1. Define dataclasses + Protocol in `base.py`.
2. `identifiers.py`: pure-fn `make_stable_id(bus, serial, model, size) -> str`. Hashes inputs to short id.
3. `macos.py`: invoke `diskutil list -plist`, parse with `plistlib`. Iterate `AllDisksAndPartitions`, build `Disk`. System = any partition mountpoint == `/`.
4. `linux.py`: invoke `lsblk -J -O -p -b`, parse JSON. Walk `blockdevices[]` of `type=="disk"`. System = mountpoint in `{/, /boot, /boot/efi}`.
5. `windows.py`: invoke `powershell -NoProfile -Command "Get-Disk | ConvertTo-Json -Depth 5"` + `Get-Partition` + `Get-Volume`. System = `IsBoot OR IsSystem`.
6. `__init__.py`: backend selector, expose `list_disks()`, `get_disk(id)`.
7. CLI `disk list`: rich-table or JSON via `--json`.
8. CLI `disk show <id>`: detailed table including partitions.
9. Unit tests: feed fixture stdout into parser, assert dataclass output. No subprocess in unit tests.
10. Integration test (host-conditional): assert `list_disks()` returns ≥1 disk on real host.

## Todo
- [ ] base.py dataclasses + Protocol
- [ ] identifiers.py stable-id helper
- [ ] macOS backend + parser tests
- [ ] Linux backend + parser tests
- [ ] Windows backend + parser tests
- [ ] CLI `disk list` + `disk show` (with `--json`)
- [ ] Backend selector
- [ ] Host-conditional integration tests

## Success Criteria
- All 3 backend parsers green on fixture data.
- `sysinstall disk list` runs on dev macOS, returns ≥1 disk including internal SSD with `is_system=True`.
- Stable IDs identical across runs for same physical disk.
- `--json` output is valid JSON.

## Risks
| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| diskutil/lsblk/PowerShell output schema drift | Med | Med | Pin minimum tool versions; tolerant parser (skip unknown keys) |
| APFS synthesized volume confusion (macOS) | High | Med | Walk `WholeDisks` only; document container handling |
| Stable ID collision (no serial) | Low | High | Fallback to `model+size+order`; mark unstable |
| Empty disks (no partitions) on Win | Low | Low | Return empty `partitions` tuple |

## Security Considerations
- All commands read-only at this stage.
- No path injection — disk IDs validated against regex `^[a-zA-Z0-9:.-]+$` before passing back to backends.

## Test Matrix
| Backend | Unit (fixtures) | Integration (host) |
|---------|------------------|---------------------|
| macOS   | yes              | macOS CI runner     |
| Linux   | yes              | Ubuntu CI runner    |
| Windows | yes              | windows-latest      |

## Rollback
Module is read-only — safe to revert anytime. Phases 03/05 depend on it; revert plus git stash on those phases too.

## Next Steps
Unblocks phase 03 (USB Ventoy install) and phase 05 (HDD partition).
