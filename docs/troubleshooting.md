# Troubleshooting Guide

Common issues and solutions when using sysinstall.

## General Issues

### "Command not found" or "sysinstall not found"
sysinstall binary not in PATH or not executable.

**Solution:**
- Use full path: `/Users/admin/Downloads/sysinstall --version`
- Or add to PATH (see `install/[windows|macos|linux].md`)
- Or copy to `/usr/local/bin/` (Linux/macOS)

### "Permission denied"
Missing execute permission or insufficient privileges for disk access.

**Solution:**
```bash
# Make executable
chmod +x ~/Downloads/sysinstall

# Or use sudo for disk operations
sudo sysinstall disk list
```

### Binary crashes with "Segmentation fault" or "Bus error"
Corrupted binary or incompatible system.

**Solution:**
1. Re-download from GitHub Releases
2. Verify checksum: `sha256sum -c sha256sum.txt`
3. Try on different machine (rule out hardware issue)

### Exit code 2 when running command
Safety gate refused operation (not an error; expected behavior).

**Solution:**
- Read error message; it explains which gate refused and why
- Use appropriate override flag (`--force-encrypted`, `--allow-fixed-disk`, `--auto-unmount`)
- Or select different disk via `--device <id>`

### No disks listed from `disk list`
Either no disks present or permission issue.

**Solution:**
```bash
# Verify you have disk enumeration privileges
sudo sysinstall disk list  # Try with sudo

# Check system permissions
# Windows: Run PowerShell as Administrator
# macOS: Run with sudo (requires T2 password if enabled)
# Linux: Run with sudo (requires CAP_SYS_ADMIN)
```

---

## Disk Enumeration Issues

### "Device not found" when specifying `--device <id>`
Device ID is incorrect or device was disconnected.

**Solution:**
```bash
# Re-list disks to get current IDs
sudo sysinstall disk list

# Device IDs may change if USB plugged/unplugged
# Verify size and vendor match before proceeding
```

### Disk shows as "encrypted" but I didn't encrypt it
System misconfigured or detected residual encryption metadata.

**Solution:**
```bash
# Verify it's really encrypted (try mounting):
sudo mount /dev/sdX1 /mnt
# If mount fails, likely encrypted; use --force-encrypted

# Or check manually:
sudo dmsetup status            # Linux LUKS
sudo diskutil info /dev/diskX  # macOS FileVault
```

### "System disk" refused (can't partition internal SSD)
Safety gate protecting your system disk.

**Solution:**
- This is intentional; never override
- Use external USB drive instead
- Or use `--allow-fixed-disk` ONLY if you're intentionally partitioning your system disk for dual-boot (risky)

### Disk not showing as "removable" (USB appears internal)
Some USB adapters don't report as removable correctly.

**Solution:**
```bash
# Force override (carefully):
sudo sysinstall disk partition --device <id> --allow-fixed-disk --confirm
```

---

## USB Creation Issues

### "Ventoy download failed"
Network issue or GitHub rate-limited.

**Solution:**
```bash
# Retry (will use cached partial download if available)
sudo sysinstall usb create --device d1 --confirm

# Or manually download Ventoy, then retry
# sysinstall will detect cached version
```

### "Cannot create USB on macOS"
Ventoy has no macOS support (upstream limitation).

**Solution:**
- Use Linux or Windows machine to create USB
- Or download pre-built Ventoy image + use `dd` (see `install/macos.md`)

### USB creation succeeded but USB doesn't boot
Bootloader not installed correctly or BIOS not set to boot USB first.

**Solution:**
1. Verify USB has Ventoy partition:
   ```bash
   lsblk | grep <usb-size>  # Should show partition d1p1, etc.
   ```

2. Check BIOS/UEFI boot order (press F2, F10, Del, etc. at startup)

3. Recreate USB:
   ```bash
   sudo sysinstall usb create --device d1 --confirm
   ```

### USB shows as "Not Ready" in Windows after creation
Ventoy USB unmounting/safety eject in Windows.

**Solution:**
```powershell
# In Windows, right-click USB drive → Eject (safe removal)
# Wait 5 seconds, unplug, re-plug
# Windows should recognize Ventoy partition
```

---

## ISO Management Issues

### "ISO not found" when adding
File path incorrect or file doesn't exist.

**Solution:**
```bash
# Check file exists
ls -la ~/Downloads/ubuntu-24.04.iso

# Use full path
sudo sysinstall iso add /home/user/Downloads/ubuntu-24.04.iso

# Not relative path
# sudo sysinstall iso add ~/Downloads/ubuntu-24.04.iso  # May not work
```

### ISO add is very slow
Large ISO copying over USB interface.

**Solution:**
- Expected for large ISOs (5+ GB)
- USB 2.0 is slow (~30 MB/s); USB 3.0+ is faster
- Use fast USB drive (Kingston, SanDisk Extreme)

### ISO list shows old ISOs after deleting
Manifest cache not refreshed.

**Solution:**
```bash
# List again (should refresh)
sudo sysinstall iso list

# If still stale, manually remove from USB:
sudo mount /dev/sdX1 /mnt
sudo rm /mnt/ubuntu-24.04.iso
sudo umount /mnt
```

### ISO checksum verification fails
Corrupted download.

**Solution:**
```bash
# Delete and re-download ISO
rm ~/Downloads/ubuntu-24.04.iso

# Download again, verify checksum before adding
sha256sum ~/Downloads/ubuntu-24.04.iso
# Compare against official checksum from ubuntu.com

# Then add to USB
sudo sysinstall iso add ~/Downloads/ubuntu-24.04.iso
```

---

## Disk Partitioning Issues

### "Refusing to partition system/boot disk"
Safety gate preventing data loss.

**Solution:**
- Select different disk via `--device <id>`
- Or use `--allow-fixed-disk` if intentionally partitioning internal disk (risky!)

### "Target disk has mounted partitions"
Partitions in use; can't modify.

**Solution:**
```bash
# Auto-unmount
sudo sysinstall disk partition --device d1 --auto-unmount --confirm

# Or manually unmount
sudo umount /mnt/windows
sudo umount /mnt/data
sudo sysinstall disk partition --device d1 --confirm
```

### "Insufficient space"
Disk too small for dual-boot layout.

**Solution:**
- Target disk must be ≥300 GB (recommended ≥512 GB)
- Current planner allocates: 260 MB EFI + 400 GB Windows + 500 GB Linux + 8 GB Swap
- Swap can be reduced: contact team for custom layout

### Partitioning succeeded but sizes don't match
Rounding errors or capacity lost to partition table.

**Solution:**
- Run `sudo sysinstall disk list` to verify actual capacities
- Slightly less space than nominal (e.g., 256 GB drive = 238 GiB actual)
- Difference is normal (GiB vs GB)

### "Partition already exists"
Trying to partition a disk with existing partitions.

**Solution:**
```bash
# Partitioner should warn and ask to delete first
# If it doesn't, delete manually:
sudo sgdisk --zap-all /dev/sdX  # Erase all partitions (Linux/macOS)
# Or use Windows Disk Management → Delete volumes

# Then retry
sudo sysinstall disk partition --device <id> --confirm
```

---

## Boot Repair Issues

### "Cannot mount /boot/efi" during boot repair
EFI partition not found or already mounted.

**Solution:**
```bash
# Run from Ubuntu live USB, from terminal:
sudo sysinstall boot repair --confirm

# Or manual fix (see tutorials/dual-boot-windows-ubuntu.md Step 4)
```

### "GRUB not found" after boot repair
GRUB not installed or corrupted.

**Solution:**
```bash
# From Ubuntu live terminal:
sudo apt-get install grub-efi-amd64
sudo mount /dev/sdX3 /mnt
sudo mount /dev/sdX1 /mnt/boot/efi
for dir in proc sys dev run; do
  sudo mount --rbind /$dir /mnt/$dir
done
sudo chroot /mnt /bin/bash
grub-install --target=x86_64-efi --efi-directory=/boot/efi
update-grub
exit
sudo reboot
```

### "efibootmgr not found"
EFI boot management tool missing.

**Solution (Ubuntu live USB):**
```bash
sudo apt-get install efibootmgr
# Then retry boot repair
sudo sysinstall boot repair --confirm
```

### Windows still boots (GRUB menu doesn't appear)
Windows bootloader is primary; GRUB sidelined.

**Solution:**
- Run boot repair again (Step 4 in `tutorials/dual-boot-windows-ubuntu.md`)
- Or manually set UEFI boot order (in BIOS setup) to prioritize GRUB

### BitLocker recovery key prompt after boot repair
Expected if Windows uses BitLocker encryption.

**Solution:**
- Have recovery key ready (saved during Windows setup)
- sysinstall boot repair doesn't decrypt; just restores boot entries
- Windows may prompt at next boot; provide recovery key or use PIN

---

## Ventoy-Specific Issues

### "Ventoy version mismatch"
Binary version differs from USB version.

**Solution:**
- Recreate USB with current sysinstall version
- Or manually update Ventoy on USB (advanced; not recommended for MVP)

### "ISO doesn't boot from Ventoy USB"
ISO format incompatible or corrupted.

**Solution:**
1. Verify ISO boots on other machines
2. Re-download ISO from official source
3. Verify checksum before adding to USB

### Ventoy SHA256 hash mismatch (v0.0.1 only)
MVP ships with placeholder Ventoy hashes; this is expected.

**Solution:**
- This is by design; MVP doesn't pin Ventoy versions
- v0.1.0 will update hashes before release
- No security issue; just advisory

---

## macOS-Specific Issues

### "sysinstall" cannot be opened" (Gatekeeper)
Unsigned binary blocked.

**Solution:**
```bash
# Bypass quarantine
xattr -d com.apple.quarantine ~/Downloads/sysinstall

# Or use Finder: Right-click → Open → Open (in warning dialog)
```

### "Operation not permitted" on Disk Utility
T2 security chip blocking.

**Solution:**
- Restart in Recovery Mode (Cmd+R at boot)
- Disable System Integrity Protection (Advanced → Security Utilities → disable SIP)
- Or use external USB adapter with disk

### Can't enumerate disks on M1 Mac
Possible Rosetta/architecture issue.

**Solution:**
- Ensure you downloaded arm64 binary (not x86)
- Run with `sudo`: `sudo sysinstall disk list`

---

## Linux-Specific Issues

### "lsblk not found"
Disk enumeration utility missing.

**Solution:**
```bash
sudo apt-get install util-linux  # Ubuntu/Debian
# or
sudo dnf install util-linux      # RHEL/Fedora
```

### "sgdisk not found"
Partitioning utility missing.

**Solution:**
```bash
sudo apt-get install gptfdisk     # Ubuntu/Debian
# or
sudo dnf install gdisk            # RHEL/Fedora
```

### "efibootmgr not found"
EFI boot management tool missing.

**Solution:**
```bash
sudo apt-get install efibootmgr   # Ubuntu/Debian
# or
sudo dnf install efibootmgr       # RHEL/Fedora
```

### "cannot access /sys/firmware/efi"
Machine is in BIOS mode (not UEFI).

**Solution:**
- sysinstall only supports UEFI (modern standard)
- For legacy BIOS machines, consider BIOS-mode dual-boot (deferred to v0.2)

---

## Windows-Specific Issues

### SmartScreen blocks execution
Unsigned binary warning.

**Solution:**
- Click "More info" → "Run anyway"
- Or add exception in Windows Defender:
  - Windows Defender → Virus & threat protection → Manage settings → Add exceptions → add sysinstall.exe

### "Access Denied" when enumerating disks
Running without Administrator privileges.

**Solution:**
```powershell
# Run PowerShell as Administrator (right-click → Run as Administrator)
.\sysinstall.exe disk list
```

### UAC prompt every command
Expected; disk operations are privileged.

**Solution:**
- Click "Yes" to allow
- sysinstall doesn't require signing; unsigned binaries trigger UAC

---

## Audit Log Review

If something goes wrong, check the audit log:

**Location:**
- Windows: `%APPDATA%\sysinstall\audit.log`
- macOS: `~/.sysinstall/audit.log`
- Linux: `~/.sysinstall/audit.log`

**Review recent entries:**
```bash
tail -50 ~/.sysinstall/audit.log
```

**Filter errors:**
```bash
grep ERROR ~/.sysinstall/audit.log
```

The log contains full context: what command ran, which gates evaluated, why an operation failed.

---

## Still Stuck?

1. **Check audit log** for exact error
2. **Review relevant tutorial** (multiboot-usb.md, dual-boot-windows-ubuntu.md)
3. **Check design-guidelines.md** for CLI conventions
4. **Search GitHub Issues** for similar problems
5. **Report issue** on GitHub with:
   - OS (Windows 11, macOS 13, Ubuntu 24.04, etc.)
   - sysinstall version (`sysinstall --version`)
   - Exact command you ran
   - Full error message
   - Last 20 lines of `audit.log`
