---
title: Linux Disk Operations Research
date: 2026-04-28
type: research-report
---

# Linux Disk Operations

## Strategy
- Enumerate: `lsblk -J -O` (JSON, all columns).
- Partition: `sgdisk` for GPT (preferred — non-interactive, scriptable). `parted` as fallback.
- Format: `mkfs.fat`, `mkfs.ntfs` (`ntfs-3g`), `mkfs.ext4`, `mkswap`.
- Settle: `udevadm settle` between operations.

## Enumeration

```bash
lsblk -J -O -p
```

`-p` → full paths (`/dev/sda1` not `sda1`). JSON has `blockdevices[]` with nested `children` for partitions.

Critical fields: `name`, `path`, `size` (bytes when `-b`), `type` (`disk`|`part`|`loop`|`rom`), `tran` (transport: `usb`/`sata`/`nvme`/...), `rm` (removable bool), `model`, `serial`, `mountpoints[]`, `pttype`, `fstype`.

## Partition (GPT) with sgdisk

```bash
# Wipe all partition tables (GPT + protective MBR)
sgdisk --zap-all /dev/sdX

# Create dual-boot layout
sgdisk \
  -n 1:0:+512M -t 1:ef00 -c 1:"EFI" \
  -n 2:0:+SIZE_W -t 2:0700 -c 2:"Windows" \
  -n 3:0:+SIZE_R -t 3:8300 -c 3:"Ubuntu" \
  -n 4:0:0       -t 4:8200 -c 4:"swap" \
  /dev/sdX
```

GUID type codes: `ef00` ESP, `0700` Microsoft basic data (NTFS), `8300` Linux filesystem, `8200` Linux swap.

## Format

```bash
mkfs.fat -F32 -n EFI /dev/sdX1
mkfs.ntfs -Q -L Windows /dev/sdX2     # ntfs-3g; -Q quick format
mkfs.ext4 -L Ubuntu /dev/sdX3
mkswap -L swap /dev/sdX4
```

For dual-boot prep on Linux host: we typically **don't pre-format Windows or Ubuntu partitions** — let each OS installer format its own slice. sysinstall just creates the partition slots (sgdisk above without mkfs steps 2-4).

## Privilege

All write ops require root. Strategy = same as macOS: detect non-root, print `sudo` re-exec hint, exit. Don't auto-spawn.

```python
def require_root_linux():
    if os.geteuid() != 0:
        sys.stderr.write(f"Re-run with sudo: sudo {' '.join(sys.argv)}\n")
        sys.exit(1)
```

## udev safety

After partitioning:

```bash
udevadm settle --timeout=10
partprobe /dev/sdX
```

Without settle, subsequent `mkfs` may race against kernel re-reading partition table, causing "device busy" errors.

## Detecting system disk

Walk mountpoints — if any partition mounted at `/`, `/boot`, or `/boot/efi`, parent disk is system. Refuse.

```python
def is_system_disk(disk_json) -> bool:
    SYSTEM_MOUNTS = {"/", "/boot", "/boot/efi", "/home", "/usr"}
    for child in disk_json.get("children", []):
        mounts = child.get("mountpoints", []) or []
        if any(m and m in SYSTEM_MOUNTS for m in mounts):
            return True
    return False
```

## Distro variance

- `sgdisk` from `gdisk` package — may not be installed by default. Detect + tell user `apt install gdisk`.
- `mkfs.ntfs` from `ntfs-3g` package.
- `parted` is everywhere; can be fallback path.
- `lsblk -O` flags vary slightly by util-linux version. Pin minimum util-linux 2.34+ (covers Ubuntu 20.04+).

## Unresolved Questions

- LUKS-encrypted disks — `lsblk` shows them; should sysinstall skip or warn? Tentative warn + refuse destructive ops.
- LVM physical volumes — if user's USB is somehow PV in a VG (unlikely but possible), `Clear-Disk` equivalent needs LVM teardown first. Punt to v2.
- BTRFS subvolumes on system disk — mountpoint detection still works (root mount is enough).
