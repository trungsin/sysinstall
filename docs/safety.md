# Safety Guarantees & Audit Logging

sysinstall is designed to be safe. This document details the 4 safety gates, when they refuse operations, and how to override them (where permitted).

## Safety Gates

All destructive operations pass through these gates before proceeding. Gates are evaluated in order; the first refusal stops execution.

### Gate 1: System Disk Gate (NEVER Overridable)
**Blocks:** Partitioning or formatting any disk identified as system/boot disk.

**Refuses if:** Target disk contains active OS installation or EFI boot partition.

**Why:** Partitioning the system disk renders the machine unbootable. No amount of confirmation should allow this.

**Error message:**
```
Error: Refusing to partition system/boot disk.
This is a safety feature to prevent data loss.
Confirm device ID: sysinstall disk list
```

**Recovery:** User must explicitly select a different disk using `--device <id>`. There is no override flag.

**Implementation:** Detection via:
- Windows: Check if disk contains Windows System Reserved partition (identified by volume label or partition GUID)
- macOS: Check if disk contains preboot volume or recovery partition
- Linux: Check if disk contains /boot or / mountpoints in `/etc/fstab`

---

### Gate 2: Encryption Gate (Override: `--force-encrypted`)
**Blocks:** Partitioning encrypted disks without explicit user intent.

**Refuses if:** Target disk has active encryption (BitLocker, FileVault, LUKS).

**Why:** Repartitioning encrypted disks may corrupt encryption metadata, causing permanent data loss and key recovery hassles.

**Error message:**
```
Error: Target disk is encrypted (BitLocker/FileVault/LUKS).
Encrypted disks may become corrupted by repartitioning.

To override: sysinstall disk partition --device <id> --force-encrypted --confirm

WARNING: You may lose access to encrypted data.
Back up recovery keys before proceeding.
```

**Override:** Use `--force-encrypted` flag. Still requires `--confirm` after displaying warning banner.

**Detection:** Platform-specific methods:
- Windows: WMI `Win32_Volume.EncryptionMethod` (BitLocker)
- macOS: `diskutil info` → `Encrypted` field (FileVault) or check `apfs list`
- Linux: `dmsetup` or `/proc/crypto` (LUKS) or `crypttab` entries

**Audit log entry when overridden:**
```
[WARN] 2026-04-28T15:30:45Z disk.partition(--force-encrypted)
  Device: /dev/sda (Samsung 970 EVO)
  Operation: Partition for dual-boot
  Override: Encryption detected but --force-encrypted provided
  User confirmed: Yes
  Result: Partitions created (user assumes risk)
```

---

### Gate 3: Fixed Disk Gate (Override: `--allow-fixed-disk`)
**Blocks:** Partitioning disks that appear to be internal (not removable).

**Refuses if:** Target disk has `removable=False` attribute (indicates internal drive).

**Why:** Internal disks are typically system or data drives. Partitioning them can make the system unbootable or destroy important data.

**Error message:**
```
Error: Target disk appears to be internal (not removable).
Partitioning may make your system unbootable.

To override: sysinstall disk partition --device <id> --allow-fixed-disk --confirm

This gate exists because USB drives are usually removable=True,
while internal SSDs/HDDs are removable=False.
```

**Override:** Use `--allow-fixed-disk` flag. Still requires `--confirm` after displaying warning banner.

**Detection:** Via `psutil.disk_partitions()` → `removable` attribute, or platform tools:
- Windows: WMI `Win32_DiskDrive.MediaType` (removable media codes)
- macOS: `diskutil info` → `Removable Media` field
- Linux: sysfs `/sys/block/sda/removable` (1 = removable, 0 = fixed)

**When to use:** If you're intentionally partitioning an internal SSD for dual-boot on the current machine, use `--allow-fixed-disk`.

**Audit log entry when overridden:**
```
[WARN] 2026-04-28T15:30:45Z disk.partition(--allow-fixed-disk)
  Device: /dev/nvme0n1 (Samsung 970 EVO, internal)
  Operation: Partition for dual-boot
  Override: Fixed disk detected but --allow-fixed-disk provided
  User confirmed: Yes
  Result: Partitions created (user assumes risk of bootability loss)
```

---

### Gate 4: Mounted Gate (Override: `--auto-unmount`)
**Blocks:** Partitioning disks with mounted partitions without explicit user intent.

**Refuses if:** Target disk has active mountpoints.

**Why:** Partitioning a disk with mounted partitions can corrupt filesystems or cause data loss if the OS tries to access the mounted filesystem while it's being modified.

**Error message:**
```
Error: Target disk has mounted partitions:
  /dev/disk2s1 mounted at /Volumes/Windows
  /dev/disk2s2 mounted at /Volumes/Data

To auto-unmount: sysinstall disk partition --device <id> --auto-unmount --confirm

These partitions will be unmounted before partitioning proceeds.
```

**Override:** Use `--auto-unmount` flag. The tool will:
1. Attempt to unmount all mounted partitions on target disk
2. Request root/admin privileges if unmount requires elevation
3. Proceed with partitioning only if all unmounts succeed
4. If any unmount fails, abort with clear error message

**Detection:** Platform-specific:
- Windows: WMI `Win32_LogicalDisk.DeviceID` → list all mounted drive letters; check if any correspond to target disk partitions
- macOS: `mount` output or `df` listing → check mountpoints against target disk
- Linux: `/proc/mounts` or `df` → check for mountpoints on target disk

**Implementation:**
```python
# Pseudocode
def check_mounted_gate(device_id: str, auto_unmount: bool) -> bool:
    mounted = find_mounted_partitions(device_id)
    if not mounted:
        return True  # Gate passes (no mounted partitions)
    
    if not auto_unmount:
        raise MountedGateRefusal(mounted)  # Gate refuses
    
    # Try to unmount
    for mount_point in mounted:
        try:
            unmount(mount_point)
        except PermissionError:
            # Will be caught as admin elevation issue
            raise
        except OSError as e:
            raise MountedGateUnmountFailed(mount_point, str(e))
    
    # Verify all unmounted
    if find_mounted_partitions(device_id):
        raise MountedGateUnmountFailed("some partitions still mounted")
    
    return True  # Gate passes (all unmounted)
```

**Audit log entry when auto-unmount used:**
```
[INFO] 2026-04-28T15:30:45Z disk.partition(--auto-unmount)
  Device: /dev/sda (Samsung 970 EVO)
  Operation: Partition for dual-boot
  Mounted partitions detected: 2
    - /dev/sda1 at /mnt/windows (unmounted)
    - /dev/sda2 at /mnt/data (unmounted)
  Override: Auto-unmount successful
  Result: Partitions created
```

---

## Gate Evaluation Order

Before **any** destructive operation:

```
1. System Disk Gate
   ├─ Is target the system/boot disk?
   │  ├─ YES → REFUSE (no override)
   │  └─ NO → continue to Gate 2
   │
2. Encryption Gate
   ├─ Is target encrypted?
   │  ├─ YES & no --force-encrypted → REFUSE
   │  ├─ YES & --force-encrypted → WARN + CONTINUE
   │  └─ NO → continue to Gate 3
   │
3. Fixed Disk Gate
   ├─ Is target an internal (non-removable) disk?
   │  ├─ YES & no --allow-fixed-disk → REFUSE
   │  ├─ YES & --allow-fixed-disk → WARN + CONTINUE
   │  └─ NO → continue to Gate 4
   │
4. Mounted Gate
   ├─ Does target have mounted partitions?
   │  ├─ YES & no --auto-unmount → REFUSE
   │  ├─ YES & --auto-unmount → UNMOUNT + CONTINUE (or FAIL if unmount errors)
   │  └─ NO → ALL GATES PASS
```

If any gate refuses, operation aborts immediately with error message + exit code 2.

---

## Audit Logging

Every operation (success or failure) is logged to the audit trail.

### Log Location
Platform-specific:
- **Windows:** `%APPDATA%\sysinstall\audit.log` (typically `C:\Users\<user>\AppData\Roaming\sysinstall\audit.log`)
- **macOS:** `~/.sysinstall/audit.log` (`/Users/<user>/.sysinstall/audit.log`)
- **Linux:** `~/.sysinstall/audit.log` (`/home/<user>/.sysinstall/audit.log`)

### Log Format
Each entry is timestamped, JSON-serializable (for parsing), with 4 levels:
- **DEBUG:** Low-level I/O (disk reads, subprocess calls)
- **INFO:** Operation milestones (partition created, USB formatted, GRUB repaired)
- **WARN:** Recoverable issues (encryption detected, gate override used)
- **ERROR:** Failures (insufficient permission, disk I/O error, validation failure)

Example entry:
```
[2026-04-28T15:30:45.123Z] [INFO] disk.partition
  Command: sysinstall disk partition --device disk1 --layout dual-boot --confirm
  User: admin
  Host: macbook-pro
  Device: disk1 (Samsung 970 EVO, serial: S123ABC)
  Operation: Create dual-boot partitions
  Gates: [PASS, PASS (no encryption), PASS (removable USB), PASS (no mounts)]
  Result: SUCCESS
  Partitions created:
    - disk1s1: EFI System (260 MB)
    - disk1s2: Windows (400 GB)
    - disk1s3: Linux (500 GB)
    - disk1s4: Swap (8 GB)
  Duration: 12.3s
```

Failure example:
```
[2026-04-28T15:31:00.456Z] [ERROR] disk.partition
  Command: sysinstall disk partition --device disk0 --confirm
  User: admin
  Host: macbook-pro
  Device: disk0 (Apple SSD, serial: APPLE001)
  Operation: Create dual-boot partitions
  Gates: [FAIL] System Disk Gate — disk is system disk (contains /boot and /)
  Result: REFUSED (exit code 2)
  Message: "Refusing to partition system/boot disk. This is a safety feature to prevent data loss."
  Duration: 0.1s
```

### Log Rotation
- **Max file size:** 100 MB per file
- **Retention:** Keep 5 rotated files (audit.log.1, audit.log.2, ..., audit.log.5)
- **Compression:** Old files are gzipped (audit.log.1.gz, etc.)
- **Format:** UTF-8 text, one entry per line (or multi-line JSON)

Example rotation:
```
~/.sysinstall/
├── audit.log           (current, <100 MB)
├── audit.log.1.gz      (100 MB, compressed)
├── audit.log.2.gz      (100 MB, compressed)
├── audit.log.3.gz      (100 MB, compressed)
├── audit.log.4.gz      (100 MB, compressed)
└── audit.log.5.gz      (oldest, 100 MB, compressed; next rotation deletes)
```

### What's Logged
**Always logged:**
- Timestamp (ISO 8601)
- Command line (exact flags + arguments)
- User who ran command (if available)
- Hostname
- Target device (ID, vendor, model, serial number, capacity)
- Operation type (partition, usb create, iso add, boot repair)
- Gate evaluation results (each gate: PASS, WARN, FAIL)
- Result (SUCCESS, FAILED, REFUSED)
- Duration (seconds)

**For successes:**
- List of partitions created / modified
- ISOs added / removed
- Boot entries restored

**For failures:**
- Exception type
- Error message
- Stack trace (truncated to last 5 frames)
- Suggested recovery action

### Sensitive Data (Not Logged)
The following are **never** logged:
- Encryption keys or passwords
- User credentials
- API keys or tokens
- PII (personal names, email addresses)
- Full disk content (only metadata)

### Querying Logs
Users can review recent operations:
```bash
# Show last 10 operations
tail -n 10 ~/.sysinstall/audit.log

# Show all ERROR entries from today
grep ERROR ~/.sysinstall/audit.log | grep $(date +%Y-%m-%d)

# Show all partition operations
grep partition ~/.sysinstall/audit.log
```

For admins/support: extract JSON entries for parsing:
```bash
# Example: extract all gate refusals
grep REFUSED ~/.sysinstall/audit.log | \
  python3 -c "import sys, json; [print(json.loads(line)) for line in sys.stdin]"
```

---

## Safety by Example

### Scenario 1: User Wants to Partition External USB Drive (Safe)
```bash
$ sysinstall disk list
┌────┬────────────────────┬──────────┬──────────┐
│ ID │ Device             │ Size     │ Removable│
├────┼────────────────────┼──────────┼──────────┤
│ d0 │ Samsung 970 EVO    │ 1.0 TB   │ No       │ ← system disk
│ d1 │ SanDisk Extreme    │ 128 GB   │ Yes      │ ← USB (safe)
└────┴────────────────────┴──────────┴──────────┘

$ sysinstall disk partition --device d1 --layout dual-boot --confirm
Gate 1 (System Disk): d1 is removable → PASS
Gate 2 (Encryption): d1 not encrypted → PASS
Gate 3 (Fixed Disk): d1 is removable → PASS
Gate 4 (Mounted): d1 has no mounts → PASS
→ Display red banner with partition details
→ Proceed (--confirm provided)
→ Create partitions
→ Log success to audit.log
```

### Scenario 2: User Accidentally Targets System Disk (Blocked)
```bash
$ sysinstall disk partition --device d0 --layout dual-boot --confirm
Gate 1 (System Disk): d0 contains /boot and / → FAIL
→ Error: "Refusing to partition system/boot disk..."
→ Exit code 2
→ Log refusal to audit.log
→ User must re-run with correct device ID (d1)
```

### Scenario 3: User Targets Encrypted USB with Override (Allowed with Warning)
```bash
$ sysinstall disk partition --device d1 --layout dual-boot --confirm
Gate 1 (System Disk): d1 is removable → PASS
Gate 2 (Encryption): d1 is encrypted (BitLocker) → FAIL
→ Error: "Target disk is encrypted..."
→ User retries with --force-encrypted

$ sysinstall disk partition --device d1 --layout dual-boot --force-encrypted --confirm
Gate 1 (System Disk): d1 is removable → PASS
Gate 2 (Encryption): d1 is encrypted but --force-encrypted provided → WARN
→ Display bold warning: "You may lose access to encrypted data"
→ Display red banner with partition details
→ Proceed (--confirm provided, user assumed risk)
→ Log override to audit.log with WARN level
```

### Scenario 4: User Targets Mounted Disk with Auto-Unmount (Allowed with Unmount)
```bash
$ mount | grep d1
/dev/d1s1 on /mnt/windows (ntfs)
/dev/d1s2 on /mnt/data (exfat)

$ sysinstall disk partition --device d1 --layout dual-boot --confirm
Gate 4 (Mounted): d1 has 2 mounted partitions → FAIL
→ Error: "Target disk has mounted partitions: /dev/d1s1 at /mnt/windows..."
→ User retries with --auto-unmount

$ sysinstall disk partition --device d1 --layout dual-boot --auto-unmount --confirm
Gate 1–3: PASS
Gate 4 (Mounted): d1 has mounts but --auto-unmount provided
  → Unmount /dev/d1s1 from /mnt/windows → SUCCESS
  → Unmount /dev/d1s2 from /mnt/data → SUCCESS
  → Verify no mounts remain → SUCCESS → PASS
→ Display red banner with partition details
→ Proceed (--confirm provided, mounts handled)
→ Create partitions
→ Log operation with unmount details to audit.log
```

---

## Admin & Support Guide

### Reviewing Audit Logs
When a user reports an issue, audit.log contains the full history:

```bash
# Check what happened during dual-boot setup
tail -50 ~/.sysinstall/audit.log

# Search for errors in last 24 hours
find ~/.sysinstall -name "audit.log*" -mtime -1 -exec \
  grep ERROR {} \;

# Export logs for support ticket
tar czf sysinstall-logs.tar.gz ~/.sysinstall/
# Upload to support portal
```

### Common Log Patterns
- **"Gate 1 FAIL"** → User tried to partition system disk; expected; no data loss
- **"Gate 2 WARN + override"** → User overrode encryption warning; inform about recovery keys
- **"Gate 4 WARN + unmount failed"** → Some process still using filesystem; help identify culprit
- **"ERROR" without gate FAIL** → Real I/O error or permission issue; troubleshoot with user

### Escalation
If user claims data loss but audit.log shows "Gate 1 FAIL" (system disk refusal), no actual modification occurred. Logs prove data integrity.

---

## Version History
- **v0.0.1 (2026-04-28):** Initial safety gates and audit logging
- **v0.1.0 (planned):** Enhanced gate messages, support for encrypted root in boot repair
- **v1.0.0 (planned):** GPG-signed audit logs, web dashboard for audit trail review
