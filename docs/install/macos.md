# Installing sysinstall on macOS

## Important Limitation
**sysinstall cannot create Ventoy USB on macOS.** This is a limitation of Ventoy itself (no macOS support). You must:
- Use a Linux or Windows machine to create the Ventoy USB, OR
- Use the `dd` workaround with a pre-built Ventoy image (see below)

sysinstall can still list disks, partition for dual-boot, and repair GRUB on macOS; USB creation is the only blocked operation.

## Download Binary
1. Go to [GitHub Releases](https://github.com/trungsin/sysinstall/releases)
2. Download `sysinstall-macos-arm64` (M1/M2/M3/M4 Macs)
3. Save to a convenient location (e.g., `~/Downloads/`)

**Note:** MVP supports Apple Silicon (M1+) only. Intel Macs are not supported.

## First Run (Gatekeeper Warning)
If binary is unsigned, macOS Gatekeeper may prevent launch:

```
"sysinstall" cannot be opened because the developer cannot be verified.
```

**To proceed:**

### Option A: Quarantine Bypass (Recommended)
```bash
# Remove quarantine attribute
xattr -d com.apple.quarantine ~/Downloads/sysinstall

# Now try running (should work without prompts)
~/Downloads/sysinstall --version
```

### Option B: Using Finder GUI
1. Open Finder, navigate to `~/Downloads/`
2. Right-click `sysinstall`
3. Click "Open"
4. Click "Open" again in the warning dialog
5. Binary is now trusted for future runs

### Option C: Allow via Security Settings (macOS 13+)
1. System Settings → Privacy & Security
2. Scroll down to "sysinstall was blocked"
3. Click "Allow Anyway"

## Make Binary Executable
```bash
chmod +x ~/Downloads/sysinstall
```

## Verify Installation
```bash
# Check version
~/Downloads/sysinstall --version
# Output: sysinstall 0.0.1

# List disks
~/Downloads/sysinstall disk list
# Output: [table of disks]
```

## Optional: Add to PATH
To run `sysinstall` from any folder without full path:

```bash
# Copy to /usr/local/bin (requires sudo)
sudo cp ~/Downloads/sysinstall /usr/local/bin/sysinstall
sudo chmod +x /usr/local/bin/sysinstall

# Test
sysinstall --version
```

Or, add Downloads to PATH:
```bash
# Add to ~/.zshrc (or ~/.bash_profile for older shells)
echo 'export PATH="$HOME/Downloads:$PATH"' >> ~/.zshrc
source ~/.zshrc

# Test
sysinstall --version
```

## Creating Ventoy USB on macOS

Since Ventoy cannot be created directly on macOS, use one of these workarounds:

### Workaround A: Use Linux or Windows Machine
1. Use a Linux or Windows computer to create Ventoy USB via:
   ```bash
   # On Linux/Windows with sysinstall:
   sysinstall usb create --device <disk-id> --confirm
   ```
2. Plug USB into Mac; it works normally

### Workaround B: Pre-Built Ventoy Image + dd
1. Download pre-built Ventoy image: [Ventoy Releases](https://github.com/ventoy/Ventoy/releases)
2. Decompress: `unzip ventoy-X.X.X-macos.zip`
3. Plug in USB drive
4. Identify USB device:
   ```bash
   diskutil list
   # Look for your USB (e.g., /dev/disk5)
   ```
5. Unmount USB:
   ```bash
   diskutil unmountDisk /dev/disk5
   ```
6. Write image to USB (replace disk5 with your device):
   ```bash
   sudo dd if=ventoy-X.X.X/ventoy.img of=/dev/rdisk5 bs=4m
   ```
7. Eject USB:
   ```bash
   diskutil eject /dev/disk5
   ```

**Why `rdisk` instead of `disk`?** Use raw device (`rdisk`) for ~10x faster write speed.

### Workaround C: Balena Etcher GUI (Easiest)
1. Download [Balena Etcher](https://www.balena.io/etcher/) for macOS
2. Install and launch Etcher
3. Click "Flash from file" → select `ventoy.img`
4. Click "Select target" → choose your USB drive
5. Click "Flash" and wait (~5 minutes)
6. Done

## Running Dual-Boot Setup
See `tutorials/dual-boot-windows-ubuntu.md` for step-by-step guide. Note: You must prepare the Ventoy USB on Linux or Windows first.

Quick start:
```bash
# After creating Ventoy USB on Linux/Windows, plug into Mac

# List disks (verify USB is present)
sysinstall disk list

# Optional: Partition internal Mac SSD for dual-boot (requires --allow-fixed-disk)
sysinstall disk partition --device <disk-id> --layout dual-boot --allow-fixed-disk --confirm

# Can also add ISOs to Ventoy USB if connected
sysinstall iso add ~/Downloads/ubuntu-24.04.iso
sysinstall iso add ~/Downloads/windows-11.iso

# Then reboot, hold Option key, choose USB boot
```

## Troubleshooting

### "Permission Denied" when running binary
Binary needs execute permission.

**Solution:**
```bash
chmod +x ~/Downloads/sysinstall
```

### "Command not found"
Binary not in PATH.

**Solution:**
```bash
# Use full path
~/Downloads/sysinstall --version

# Or add to PATH (see "Optional: Add to PATH" section)
```

### "Operation not permitted" during disk operations
sysinstall needs elevated privileges for raw disk access.

**Solution:**
```bash
# Run with sudo
sudo ~/Downloads/sysinstall disk list
```

### Gatekeeper won't allow binary even after workarounds
File may be corrupted or signature invalid.

**Solution:**
1. Delete binary: `rm ~/Downloads/sysinstall`
2. Download again from GitHub Releases
3. Retry quarantine removal: `xattr -d com.apple.quarantine ~/Downloads/sysinstall`

### "Cannot create USB on macOS" error
Expected behavior. Ventoy upstream has no macOS support.

**Solution:**
- Use Workaround A: Create USB on Linux/Windows machine
- Use Workaround B: Download pre-built Ventoy image, use dd
- Use Workaround C: Use Balena Etcher GUI

### System refuses to boot from USB
1. Ensure USB was created with Ventoy (check for `ventoy` partition)
2. Restart Mac, hold Option key during boot
3. Select USB drive from boot menu
4. If still fails, try recreating USB on Linux/Windows machine

## Security Notes
- Binary is unsigned; Gatekeeper may warn (expected, documented, harmless)
- Audit log saved to `~/.sysinstall/audit.log` — review if needed
- All disk operations logged for safety auditing
- macOS will require `sudo` for privileged disk operations

## Next Steps
- Read `safety.md` to understand the 4 safety gates
- Follow `tutorials/dual-boot-windows-ubuntu.md` for complete dual-boot walkthrough
- Check `troubleshooting.md` for additional error fixes

## Supported Hardware
- **CPU:** Apple Silicon (M1, M2, M3, M4, M4 Pro/Max)
- **OS:** macOS 12 Monterey or later (12.1+)
- **Intel Macs:** Not supported in MVP; use Linux or Windows binary on Intel hardware

## Support
- Issues: [GitHub Issues](https://github.com/trungsin/sysinstall/issues)
- Docs: [Full Documentation](../README.md)
