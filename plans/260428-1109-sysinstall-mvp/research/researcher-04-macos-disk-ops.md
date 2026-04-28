---
title: macOS Disk Operations Research
date: 2026-04-28
type: research-report
---

# macOS Disk Operations

## Strategy
Shell out to `diskutil` (plist output → `plistlib`). Raw block writes need root → `sudo` re-exec.

## Enumeration

```bash
diskutil list -plist                    # all disks/partitions
diskutil info -plist /dev/diskN          # detailed disk info
diskutil info -plist disk1s1             # specific volume
```

Parse with stdlib:

```python
import plistlib, subprocess
data = plistlib.loads(
    subprocess.run(["diskutil", "list", "-plist"], capture_output=True, check=True).stdout
)
for whole in data["AllDisksAndPartitions"]:
    ...
```

Key fields: `DeviceIdentifier`, `Size`, `Internal` (bool — system-disk hint), `Removable`, `Partitions[]`, `APFSVolumes[]`.

## APFS edge case

Modern macOS uses APFS containers — one physical disk → one container → many synthesized volumes. `AllDisksAndPartitions` includes both `Partitions` (slice list) and `APFSVolumes` (synthesized).

For sysinstall purposes (USB creation): we operate on whole disks (`/dev/diskN`), ignoring synthesized volumes. Container handling is auto by `diskutil eraseDisk`.

## Operations

```bash
# Unmount whole disk before write
diskutil unmountDisk /dev/diskN

# Erase + repartition (GPT)
diskutil eraseDisk JHFS+ "Name" GPT /dev/diskN

# Eject when done
diskutil eject /dev/diskN
```

For Ventoy on macOS: **NOT SUPPORTED upstream**. See researcher-01-ventoy-cli.md. Strategy:
- macOS host: USB-create returns "unsupported, use Linux/Windows host" message. (Decision: option 3 from ventoy doc.)
- macOS host can still: enumerate disks, format/partition non-Ventoy USBs, do ISO management on already-Ventoy'd USBs (write to FAT32 partition mounted by macOS automatically).

## Permissions / Elevation

- Read-only `diskutil list/info` — unprivileged.
- `eraseDisk`, `unmountDisk`, raw `dd` on `/dev/rdiskN` — require root.
- macOS lacks `runas`-style auto-prompt. Strategy: detect `os.geteuid() != 0`, print clear `sudo` re-exec instruction, exit.

```python
def require_root_macos():
    if os.geteuid() != 0:
        sys.stderr.write(
            "This command needs root. Re-run:\n"
            f"  sudo {' '.join(sys.argv)}\n"
        )
        sys.exit(1)
```

Avoid auto-spawning `sudo` from script — TUI gets ugly + breaks PyInstaller-bundled Python path resolution.

## SIP / TCC

- System Integrity Protection blocks write to system volume regardless of root. `diskutil` respects SIP.
- Full Disk Access (TCC) — needed for some metadata reads. `diskutil` doesn't need it. We're safe.

## Apple Silicon notes

- `/dev/disk0` is internal NVMe — hosts macOS + APFS containers. Always `Internal=True`.
- USB sticks plugged in show as `/dev/disk2`+ depending on count. Always `Internal=False` + `Removable=True` (or `Ejectable=True`).
- Code signing: PyInstaller binary needs notarization to run on Apple Silicon w/o Gatekeeper warning. See researcher-07.

## Unresolved Questions

- macOS sealed system volume — does `diskutil` correctly mark every APFS slice on disk0 as system? Tentative yes, but worth empirical check.
- T2 chip Macs (Intel pre-2020) — encrypted internal SSD. Read-only enumeration still works; writes blocked.
- USB-C hubs — multi-disk presented as single bus. Bus type may report `usb` for all → enumeration correct but UI must show per-disk.
