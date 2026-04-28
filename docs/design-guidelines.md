# CLI Design Guidelines

## Command Structure
sysinstall is organized as Typer subcommands in 4 groups:

```
sysinstall disk      [list, partition, list-efi]
sysinstall usb       [create, info]
sysinstall iso       [add, remove, list]
sysinstall boot      [repair, detect, list]
```

## Safety & Confirmation Pattern
All destructive operations follow this pattern:

### 1. Red Banner Warning
Before asking for confirmation, print a prominent warning with human-readable details:
```
╭─────────────────────────────────────────────────────────────╮
│ WARNING: This operation will modify your disk.              │
│                                                              │
│ Device: Samsung 970 EVO (1TB)                               │
│ ID: disk2                                                   │
│ Partitions to create:                                       │
│   - EFI System (260 MB)                                     │
│   - Windows (400 GB)                                        │
│   - Linux (500 GB)                                          │
│   - Swap (8 GB)                                             │
│                                                              │
│ This cannot be undone. Back up your data.                  │
╰─────────────────────────────────────────────────────────────╯
```

### 2. Confirmation Requirement
Require one of:
- **Interactive:** Prompt "Type YES to continue: "
- **Non-interactive:** Require `--confirm` flag (for scripting)

Both paths require explicit user intent; never default to proceeding.

### 3. Dry-Run Preview
Support `--dry-run` flag to preview without applying:
```bash
$ sysinstall disk partition --device disk2 --layout dual-boot --dry-run
[DRY RUN] Would create partitions on Samsung 970 EVO:
  - Partition 1: EFI System (260 MB) at /dev/disk2s1
  - Partition 2: Windows (400 GB) at /dev/disk2s2
  - Partition 3: Linux (500 GB) at /dev/disk2s3
  - Partition 4: Swap (8 GB) at /dev/disk2s4
```

## Flag Conventions

### Device Selection
```bash
--device <id>
```
Required for multi-disk operations. IDs are stable (serial-based, not `/dev/sda`).

Example:
```bash
sysinstall disk list
# Output:
# ID: disk0  Apple SSD SM1000G (1.0 TB)
# ID: disk1  Samsung 970 EVO (500 GB)
$ sysinstall disk partition --device disk1 --layout dual-boot --confirm
```

### Confirmation & Dry-Run
```bash
--confirm          # Skip interactive prompt (for scripting)
--dry-run          # Preview without applying
```

Both can be combined; `--dry-run --confirm` still previews but doesn't prompt.

### Safety Overrides
Override specific gates with explicit flags:

**`--force-encrypted`** — Proceed on encrypted disks
```bash
$ sysinstall disk partition --device disk1 --force-encrypted --confirm
# Prints: WARNING: Target disk is encrypted (BitLocker/LUKS). 
#         Partitioning may corrupt recovery keys. Proceed? [y/N]
```

**`--allow-fixed-disk`** — Proceed on non-removable disks (internal drives)
```bash
$ sysinstall disk partition --device disk0 --allow-fixed-disk --confirm
# Prints: WARNING: Target disk appears to be internal (not removable).
#         Proceeding may make your system unbootable. Confirm? [y/N]
```

**`--auto-unmount`** — Automatically unmount mounted partitions
```bash
$ sysinstall disk partition --device disk1 --auto-unmount --confirm
# Unmounts /mnt/windows and /mnt/data, then proceeds
```

## Output Modes

### Default (Human-Readable)
Colored text with tables and progress:
```bash
$ sysinstall disk list
┌────┬───────────────────────────────┬──────────────┬──────────┐
│ ID │ Model                         │ Size         │ Removable│
├────┼───────────────────────────────┼──────────────┼──────────┤
│ d0 │ Apple SSD SM1000G             │ 1.0 TB       │ No       │
│ d1 │ Samsung 970 EVO Plus          │ 500 GB       │ Yes      │
│ d2 │ SanDisk Extreme Pro (USB)     │ 128 GB       │ Yes      │
└────┴───────────────────────────────┴──────────────┴──────────┘

$ sysinstall iso list
┌──────────────────────┬───────────┐
│ ISO                  │ Size      │
├──────────────────────┼───────────┤
│ ubuntu-24.04.iso     │ 4.2 GB    │
│ windows-11.iso       │ 6.1 GB    │
└──────────────────────┴───────────┘
```

### JSON Output (Scripting)
When `--json` is specified, output structured data:
```bash
$ sysinstall disk list --json
[
  {
    "id": "disk0",
    "vendor": "Apple",
    "model": "SSD SM1000G",
    "capacity_bytes": 1099511627776,
    "removable": false,
    "encrypted": false
  },
  {
    "id": "disk1",
    "vendor": "Samsung",
    "model": "970 EVO Plus",
    "capacity_bytes": 549755813888,
    "removable": true,
    "encrypted": false
  }
]
```

Available commands with `--json`:
- `disk list --json`
- `disk list-efi --json`
- `usb info --json`
- `iso list --json`
- `boot detect --json`
- `boot list --json`

## Exit Codes

| Code | Meaning | Example |
|------|---------|---------|
| 0 | Success | Operation completed without errors |
| 1 | Runtime error | Disk I/O failure, subprocess crash, invalid input |
| 2 | Safety refusal | System disk gate, encryption gate, permission denied |

Example:
```bash
$ sysinstall disk partition --device disk0 --confirm
# disk0 is system disk
Error: Refusing to partition system disk. Use --allow-fixed-disk to override.
$ echo $?
2
```

## Error Messages
All errors follow this pattern:

### Short Error (user-facing console)
```
Error: Could not read disk list: Permission denied
Try: Run with elevated privileges (sudo on Linux/macOS, admin on Windows)
```

### Long Error (audit log)
```
[ERROR] 2026-04-28T15:30:45Z disk.list_disks()
  Operation: List attached disks
  Platform: linux
  Exception: PermissionError: Operation not permitted
  Context: Attempted to read /proc/partitions without CAP_SYS_ADMIN
  Stacktrace: [full Python traceback]
```

## Progress & Feedback
For long-running operations (USB creation, partitioning, boot repair), provide progress:

```bash
$ sysinstall usb create --device disk1 --confirm
Downloading Ventoy 1.1.05...     [████████████░░░░░░░░] 65%
Formatting USB...                [██████████████████░░] 90%
Writing bootloader...            [████████████████████] 100%
✓ USB created successfully
```

## macOS USB-Create Limitation
macOS hosts cannot create Ventoy USB (upstream limitation):
```bash
$ sysinstall usb create --device disk1 --confirm
Error: Ventoy USB creation is not supported on macOS.
Note: Use a Linux or Windows machine to create the Ventoy USB.
      Alternatively, download a pre-built Ventoy image and use:
      $ dd if=ventoy.img of=/dev/rdisk1 bs=4m
```

Users are directed to `install/macos.md` for workarounds.

## Safety Gate Messages
Each gate has a standard message when refusing:

### System Disk Gate (NEVER overridable)
```
Error: Refusing to partition system/boot disk.
This is a safety feature to prevent data loss.
Confirm device ID: sysinstall disk list
```

### Encryption Gate
```
Error: Target disk is encrypted (BitLocker/FileVault/LUKS).
Encrypted disks may become corrupted by repartitioning.
To override: sysinstall disk partition --device <id> --force-encrypted --confirm
Note: You may lose access to encrypted data. Back up recovery keys first.
```

### Mounted Gate
```
Error: Target disk has mounted partitions:
  /dev/disk1s1 mounted at /mnt/windows
  /dev/disk1s2 mounted at /mnt/data
To auto-unmount: sysinstall disk partition --device <id> --auto-unmount --confirm
```

### Fixed Disk Gate
```
Error: Target disk appears to be internal (not removable).
Partitioning may make your system unbootable.
To override: sysinstall disk partition --device <id> --allow-fixed-disk --confirm
```

## Help & Discovery
All commands support `--help`:
```bash
$ sysinstall disk partition --help
Usage: sysinstall disk partition [OPTIONS]

Partition a disk for dual-boot (Windows + Linux).

Options:
  --device TEXT              Device ID (required). See: sysinstall disk list
  --layout TEXT              Partition layout [dual-boot]
  --confirm                  Skip confirmation prompt
  --dry-run                  Preview without applying
  --force-encrypted          Override encryption refusal
  --allow-fixed-disk         Override internal-disk refusal
  --auto-unmount             Auto-unmount mounted partitions
  --json                     Output JSON instead of human-readable
  --help                     Show this message
```

## Version & Help
```bash
$ sysinstall --version
sysinstall 0.0.1

$ sysinstall --help
Usage: sysinstall [OPTIONS] COMMAND [ARGS]...

  Multi-boot USB + dual-boot CLI for Windows and Linux.

Commands:
  disk      Disk enumeration and partitioning
  usb       Ventoy USB creation
  iso       ISO image management
  boot      Bootloader detection and repair

$ sysinstall disk --help
Usage: sysinstall disk [OPTIONS] COMMAND [ARGS]...

  Disk enumeration and partitioning for dual-boot setup.

Commands:
  list          List attached disks
  partition     Partition for dual-boot
  list-efi      List EFI boot entries
```
