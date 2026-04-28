---
title: Cross-Platform Disk Enumeration Research
date: 2026-04-28
type: research-report
---

# Cross-Platform Disk Enumeration

## Verdict
**Hybrid approach**: `psutil` for mounted-partition enumeration + **shell out to native tools for raw block devices**. `psutil.disk_partitions()` covers mounted FS but does NOT list unpartitioned/unmounted disks (which is what we need for USB creation + partitioning).

## Why psutil alone is insufficient

`psutil.disk_partitions()` returns mounted FS only. For sysinstall we need:
1. List **all physical disks** including blank/unmounted USBs
2. Distinguish removable vs fixed
3. Identify the **system/boot disk** (for safety refusal)
4. Get serial numbers (for stable disk targeting across reboots)

These require platform-specific calls.

## Per-platform tooling

### macOS — `diskutil list -plist`

```bash
diskutil list -plist
```

- Returns **XML plist**, parse with stdlib `plistlib`.
- Top-level keys: `AllDisks`, `AllDisksAndPartitions`, `WholeDisks`.
- Per-disk: `DeviceIdentifier`, `Size`, `Content`, `Partitions[]`, `Internal` (bool — system disk hint), `Removable`.
- Permissions: read-only enumeration is **unprivileged**. Raw writes (`/dev/rdiskN`) require root.

### Linux — `lsblk -J -O`

```bash
lsblk -J -O
```

- `-J` → JSON, `-O` → all columns.
- Per-device fields used: `name`, `path`, `size`, `type` (disk/part), `tran` (usb/sata/nvme), `rm` (removable), `mountpoints`, `serial`, `model`, `pttype`, `fstype`.
- udev caveat: run `udevadm settle` first if device just inserted.
- Permissions: enumeration unprivileged. Writes need root.

### Windows — PowerShell `Get-Disk` + `Get-Partition` (preferred over WMIC)

```powershell
Get-Disk | ConvertTo-Json -Depth 4
Get-Partition | ConvertTo-Json -Depth 4
Get-Volume | ConvertTo-Json -Depth 4
```

- Returns structured JSON.
- Per-disk: `Number`, `FriendlyName`, `Size`, `BusType` (USB/SATA/NVMe), `IsSystem`, `IsBoot`, `PartitionStyle`.
- `IsBoot` / `IsSystem` flags are gold for safety layer — **refuse if either is true**.
- WMIC is deprecated in Win11 24H2+. Use PowerShell cmdlets.
- Permissions: enumeration unprivileged. `New-Partition`/`Set-Disk`/clean require Admin (UAC).

## Unified Abstraction

```python
@dataclass
class Disk:
    id: str              # platform-stable id (PhyDrive#, /dev/sdX, /dev/diskN)
    path: str            # raw device path
    size_bytes: int
    model: str
    serial: str | None
    bus: Literal["usb","sata","nvme","scsi","unknown"]
    is_removable: bool
    is_system: bool      # boot/system disk — refuse writes
    partitions: list[Partition]

@dataclass
class Partition:
    id: str
    fs_type: str | None
    size_bytes: int
    mountpoints: list[str]
    label: str | None
```

Backend resolved at runtime:

```
disks/
  __init__.py          # public: list_disks(), get_disk(id), refresh()
  base.py              # ABCs + dataclasses
  macos.py             # diskutil + plistlib
  linux.py             # lsblk + json
  windows.py           # powershell + json
```

`__init__.py` selects backend via `sys.platform`.

## Why not pySMART / diskcache

- `pySMART` — SMART data only, doesn't enumerate raw disks.
- `diskcache` — unrelated (cache library, name collision).
- `psutil` — supplement for mounted-FS metadata only.

## Safety: Detecting System Disk

| Platform | Signal |
|----------|--------|
| macOS    | `Internal=True` AND mounts contain `/` → system |
| Linux    | partition mountpoint == `/` OR `/boot/efi` → parent disk is system |
| Windows  | `Get-Disk.IsSystem` OR `IsBoot` flag |

Refuse all destructive ops if `disk.is_system == True`. Hard-coded, not overridable.

## Unresolved Questions

- macOS APFS containers: a single physical disk hosts multiple synthesized volumes. How to expose them? (Tentative: list `WholeDisks` only; ignore synthesized.)
- Windows Storage Spaces virtual disks — currently not handled. v2 problem.
- NVMe namespaces on Linux — `nvme0n1` vs `nvme0n1p1` parsing edge case.
