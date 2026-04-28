# Tutorial: Creating a Multi-Boot USB with Ventoy

This tutorial walks through creating a Ventoy USB drive with multiple ISOs (Windows, Ubuntu, tools) and booting from them.

## Prerequisites
- Linux or Windows machine (macOS cannot create Ventoy; see `install/macos.md` for workaround)
- USB drive ≥128 GB
- 3-5 ISO files (Windows 11, Ubuntu 24.04, etc.)
- sysinstall binary (see `install/[windows|linux].md`)

## Step 1: Plug in USB Drive and List Disks

```bash
# Linux
sudo sysinstall disk list

# Windows (PowerShell)
.\sysinstall.exe disk list
```

Output:
```
┌────┬────────────────────────────┬──────────┬──────────┐
│ ID │ Device                     │ Size     │ Removable│
├────┼────────────────────────────┼──────────┼──────────┤
│ d0 │ Samsung 970 EVO (system)   │ 1.0 TB   │ No       │
│ d1 │ SanDisk Extreme Pro (USB)  │ 128 GB   │ Yes      │
└────┴────────────────────────────┴──────────┴──────────┘
```

**Verify:** Find your USB drive (typically the one marked "Removable" with matching size). In this case: `d1`.

## Step 2: Create Ventoy USB

```bash
# Linux
sudo sysinstall usb create --device d1 --confirm

# Windows
.\sysinstall.exe usb create --device d1 --confirm
```

Expected output:
```
Downloading Ventoy 1.1.05...     [████████████░░░░░░░░] 65%
Formatting USB...                [██████████████████░░] 90%
Writing bootloader...            [████████████████████] 100%
✓ USB created successfully
```

**What happened:**
1. Downloaded Ventoy bootloader (~20 MB)
2. Formatted USB with GPT partition table
3. Wrote Ventoy bootloader to partition
4. Created `ventoy.json` manifest (initially empty)

**Verification:**
Plug USB into any computer and look for a "Ventoy" partition. On Windows, it appears as a removable drive. On Linux, `lsblk` shows a new partition.

## Step 3: Add ISOs to USB

Copy ISO files to the USB's Ventoy partition. You can either:

### Option A: Use sysinstall (Recommended)
```bash
# Linux
sudo sysinstall iso add ~/Downloads/windows-11.iso
sudo sysinstall iso add ~/Downloads/ubuntu-24.04.iso
sudo sysinstall iso add ~/Downloads/gparted-live.iso

# Windows
.\sysinstall.exe iso add C:\Users\<user>\Downloads\windows-11.iso
.\sysinstall.exe iso add C:\Users\<user>\Downloads\ubuntu-24.04.iso
.\sysinstall.exe iso add C:\Users\<user>\Downloads\gparted-live.iso
```

Output:
```
Adding windows-11.iso (6.1 GB)...  [████████████████████] 100%
✓ ISO added
Adding ubuntu-24.04.iso (4.2 GB)... [████████████████████] 100%
✓ ISO added
Adding gparted-live.iso (650 MB)... [████████████████████] 100%
✓ ISO added
```

### Option B: Drag-and-Drop (Manual)
1. Plug USB into any machine
2. Locate "Ventoy" partition (appears as removable drive)
3. Drag ISO files directly into the partition's root folder
4. sysinstall auto-detects ISOs when queried

## Step 4: Verify ISOs Are Present

```bash
# List ISOs on the USB
sysinstall iso list
```

Output:
```
┌──────────────────────┬───────────┐
│ ISO Name             │ Size      │
├──────────────────────┼───────────┤
│ windows-11.iso       │ 6.1 GB    │
│ ubuntu-24.04.iso     │ 4.2 GB    │
│ gparted-live.iso     │ 650 MB    │
└──────────────────────┴───────────┘
Ventoy USB info:
  Total capacity: 128 GB
  Used: 10.75 GB
  Free: 117.25 GB
```

## Step 5: Boot from USB and Select ISO

1. **Reboot the target computer**
2. **Press boot menu key during startup:**
   - Dell: F12
   - HP/Lenovo: F9
   - ASUS: Esc
   - Acer: F12
   - Generic: Esc or Del
3. **Select USB drive from boot menu**
4. **Wait for Ventoy boot screen:**

```
╔═══════════════════════════════════════════════════════════╗
║                   VENTOY BOOT MENU                        ║
║                                                            ║
║  1. windows-11.iso                                        ║
║  2. ubuntu-24.04.iso                                      ║
║  3. gparted-live.iso                                      ║
║                                                            ║
║  Press [↑/↓] to select, [Enter] to boot                  ║
╚═══════════════════════════════════════════════════════════╝
```

5. **Select ISO and press Enter**
6. **Wait for ISO to load (30-60 seconds)**
7. **Follow OS installer prompts**

## Step 6: Example: Install Ubuntu from USB

After selecting `ubuntu-24.04.iso`:

```
[Ventoy is loading ISO...]

Welcome to Ubuntu 24.04 LTS Installer

What would you like to do?
1. Install Ubuntu
2. Try Ubuntu (live environment)
3. OEM Install
4. CLI install

Select: 1
```

Follow the installer. When prompted for disk, choose your target disk (not the USB). The installer will partition and install.

## Step 7: Remove or Add More ISOs

### Remove an ISO
```bash
sysinstall iso remove windows-11.iso
# Output: ✓ Removed windows-11.iso
```

### Add More ISOs
```bash
sysinstall iso add ~/Downloads/debian-12.iso
sysinstall iso add ~/Downloads/fedora-39.iso
# Output: ✓ ISO added (repeated for each)
```

## Common Boot Issues

### USB Won't Boot
1. Verify BIOS/UEFI is set to boot USB first (change in boot menu)
2. Ensure USB was created with sysinstall (check for Ventoy partition)
3. Try recreating USB: `sudo sysinstall usb create --device d1 --confirm`

### Wrong ISO Selected
Ventoy allows selecting from the menu; press Esc to go back and choose again.

### ISO Corrupted During Copy
Re-add it:
```bash
sysinstall iso remove corrupted.iso
sysinstall iso add ~/Downloads/corrupted.iso
```

## Tips & Tricks

### Persistent Live USB
Ventoy supports persistent volumes (`. dat` files) for live environments. This is deferred to v0.2; for now, live boots are ephemeral (changes not saved).

### BIOS vs UEFI Boot
- **UEFI (modern):** Ventoy detected automatically; works out-of-box
- **BIOS (legacy):** Ventoy has limited support; try BIOS-mode option in boot menu if available

### Speed Up ISO Copying
For large ISOs (>5 GB), use fast USB 3.0+ drives:
```bash
# Identify USB device
lsblk | grep <usb-size>

# Copy manually (faster for large files)
sudo dd if=ubuntu-24.04.iso of=/dev/<disk> bs=4m
```

## Next Steps
- See `dual-boot-windows-ubuntu.md` for dual-boot setup after USB creation
- See `troubleshooting.md` if boot fails
- See `safety.md` to understand safety gates during partitioning
