# Installing sysinstall on Linux

## Download Binary
1. Go to [GitHub Releases](https://github.com/USER/sysinstall/releases)
2. Download `sysinstall-linux-x64` (latest version)
3. Download `sha256sum.txt` alongside
4. Save to a convenient location (e.g., `~/Downloads/`)

## Verify Checksum (Recommended)
Before running, verify the binary hasn't been tampered with:

```bash
cd ~/Downloads
sha256sum -c sha256sum.txt | grep sysinstall-linux-x64
# Output: sysinstall-linux-x64: OK
```

If output doesn't show "OK", download again from official GitHub Releases.

## Make Binary Executable
```bash
chmod +x ~/Downloads/sysinstall-linux-x64
```

## Verify Installation
```bash
# Check version
~/Downloads/sysinstall-linux-x64 --version
# Output: sysinstall 0.0.1

# List disks (requires root/sudo for disk enumeration)
sudo ~/Downloads/sysinstall-linux-x64 disk list
# Output: [table of disks]
```

## Optional: Install System-Wide
To make `sysinstall` available globally without path prefixes:

### Option A: Copy to /usr/local/bin (Recommended)
```bash
sudo cp ~/Downloads/sysinstall-linux-x64 /usr/local/bin/sysinstall
sudo chmod +x /usr/local/bin/sysinstall

# Test
sysinstall --version
```

### Option B: Create Symbolic Link
```bash
sudo ln -s ~/Downloads/sysinstall-linux-x64 /usr/local/bin/sysinstall

# Test
sysinstall --version
```

### Option C: Add Download Folder to PATH
```bash
# Add to ~/.bashrc or ~/.zshrc
echo 'export PATH="$HOME/Downloads:$PATH"' >> ~/.bashrc
source ~/.bashrc

# Test
sysinstall --version
```

## Running Dual-Boot Setup
See `tutorials/dual-boot-windows-ubuntu.md` for step-by-step guide.

Quick start:
```bash
# Plug in USB drive

# List disks (identify USB)
sudo sysinstall disk list

# Create Ventoy USB (replace <disk-id> with actual ID)
sudo sysinstall usb create --device <disk-id> --confirm

# Add Windows ISO
sudo sysinstall iso add ~/Downloads/windows-11.iso

# Add Ubuntu ISO
sudo sysinstall iso add ~/Downloads/ubuntu-24.04.iso

# User then boots from USB and installs OS manually
```

## Privilege Requirements
sysinstall requires root/sudo for disk operations:
- `disk list` — enumerate disks (requires CAP_SYS_ADMIN or root)
- `disk partition` — create/modify partitions (requires root)
- `usb create` — format USB drive (requires root)
- `iso add/remove` — modify Ventoy USB (requires root)
- `boot repair` — modify EFI/GRUB (requires root)

Simply prefix commands with `sudo`:
```bash
sudo sysinstall usb create --device disk1 --confirm
```

## Optional Dependency: boot-repair Package
For `sysinstall boot repair` to work on Ubuntu/Debian systems, the system should have the `boot-repair` package available (if not already installed):

```bash
# Optional: install boot-repair (enhances boot repair functionality)
sudo apt-get install boot-repair

# Then sysinstall boot repair works from Ubuntu live USB
```

The `boot-repair` package is optional; sysinstall has fallback implementations for basic GRUB repair.

## Troubleshooting

### "Permission Denied"
Either binary isn't executable or you need root privileges.

**Solution:**
```bash
# Make executable
chmod +x ~/Downloads/sysinstall-linux-x64

# Or use sudo
sudo ~/Downloads/sysinstall-linux-x64 disk list
```

### "Command not found"
Binary not in PATH.

**Solution:**
```bash
# Use full path
~/Downloads/sysinstall-linux-x64 --version

# Or install to /usr/local/bin (see "Optional: Install System-Wide")
```

### "Device not found" or "Cannot access disk"
Device ID may be wrong, or you need elevated privileges.

**Solution:**
```bash
# Re-list disks with proper privileges
sudo sysinstall disk list

# Verify device ID matches your USB (check Size and Removable columns)
```

### "Segmentation fault" or "Bus error"
Rare; usually indicates corrupted binary or incompatible glibc version.

**Solution:**
1. Delete binary: `rm ~/Downloads/sysinstall-linux-x64`
2. Download again from GitHub Releases
3. Verify checksum: `sha256sum -c sha256sum.txt`
4. Try again: `sudo sysinstall disk list`

### "lsblk not found" or "sgdisk not found"
Missing system utilities for disk enumeration/partitioning.

**Solution (Ubuntu/Debian):**
```bash
sudo apt-get install util-linux                # for lsblk
sudo apt-get install gptfdisk                  # for sgdisk
sudo apt-get install efibootmgr                # for EFI boot management
sudo apt-get install grub-efi-amd64            # for GRUB on UEFI
```

**Solution (RHEL/CentOS/Fedora):**
```bash
sudo dnf install util-linux gdisk efibootmgr grub2-efi-x64
```

### "Cannot open /dev/sdX: Read-only file system"
Disk is read-only (write-protected, or filesystem mounted as read-only).

**Solution:**
```bash
# Check if filesystem is mounted
mount | grep /dev/sd

# Try auto-unmounting
sudo sysinstall disk partition --device <id> --auto-unmount --confirm
```

## Security Notes
- Binary is unsigned (ELF, no signatures); no SmartScreen/Gatekeeper on Linux
- Audit log saved to `~/.sysinstall/audit.log` — review if needed
- All disk operations logged for safety auditing
- Running with sudo required for disk access (principle of least privilege)

## Supported Distributions
sysinstall builds on Ubuntu 22.04 and should work on:
- Ubuntu 20.04+
- Debian 11+
- Fedora 38+
- RHEL 8+
- Arch Linux
- Any glibc 2.31+ system

## Next Steps
- Read `safety.md` to understand the 4 safety gates
- Follow `tutorials/dual-boot-windows-ubuntu.md` for complete dual-boot walkthrough
- Check `troubleshooting.md` for additional error fixes

## Support
- Issues: [GitHub Issues](https://github.com/USER/sysinstall/issues)
- Docs: [Full Documentation](../README.md)
