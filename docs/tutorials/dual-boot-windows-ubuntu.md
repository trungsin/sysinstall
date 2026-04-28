# Tutorial: Complete Dual-Boot Setup (Windows + Ubuntu)

This is a **start-to-finish** guide for installing Windows and Ubuntu side-by-side on a single disk.

## Overview
A dual-boot system means your computer can boot either Windows or Ubuntu, selected from a GRUB menu at startup.

**Boot order:** UEFI → Ventoy USB (optional) → Hard disk → GRUB menu → Choose Windows or Ubuntu.

## Prerequisites
- sysinstall installed on Linux or Windows machine
- Target machine with ≥512 GB disk (recommended: 256 GB Windows + 256 GB Ubuntu + 16 GB Swap)
- Ventoy USB created with Windows 11 and Ubuntu 24.04 ISOs (see `tutorials/multiboot-usb.md`)
- Ubuntu 24.04 live USB (for boot repair) — can use the Ventoy USB
- Backup any important data on target disk (this process erases it)

## Step 0: Prepare ISOs and USB Drives

### Option A: Single Ventoy USB (Recommended)
Create one Ventoy USB with both Windows 11 and Ubuntu 24.04 ISOs.

```bash
# On Linux/Windows machine with sysinstall:
sudo sysinstall usb create --device <usb-id> --confirm
sudo sysinstall iso add windows-11.iso
sudo sysinstall iso add ubuntu-24.04.iso
```

### Option B: Two Separate USBs
- USB #1: Ventoy with Windows 11
- USB #2: Ventoy with Ubuntu 24.04
(Simplifies per-step booting; requires two USB drives)

## Step 1: Partition the Target Disk

**CRITICAL:** This step erases your disk. Ensure you have backups.

On a machine with sysinstall (not the target machine; you'll boot the target from USB), partition the disk:

```bash
# List disks (identify external target disk or if internal, use --allow-fixed-disk)
sudo sysinstall disk list

# Example output:
# ID: d0  Samsung 970 EVO (system disk, 1 TB, internal) — DO NOT TOUCH
# ID: d1  WD Blue SSD (512 GB, external) — TARGET DISK

# Partition for dual-boot
# If d1 is removable (external USB for testing):
sudo sysinstall disk partition --device d1 --layout dual-boot --confirm

# If d1 is internal (your main drive):
sudo sysinstall disk partition --device d1 --layout dual-boot --allow-fixed-disk --confirm
```

Expected output:
```
WARNING: This operation will modify your disk.
Device: WD Blue SSD (512 GB)
Partitions to create:
  - EFI System (260 MB)
  - Windows (256 GB)
  - Linux (256 GB)
  - Swap (8 GB)

This cannot be undone. Back up your data.
Type YES to continue: YES

Creating partitions... [████████████████████] 100%
✓ Dual-boot partitions created

New layout:
  /dev/sda1 — EFI System (260 MB)
  /dev/sda2 — Windows NTFS (256 GB)
  /dev/sda3 — Linux (unformatted, 256 GB)
  /dev/sda4 — Swap (8 GB)
```

**What happened:**
- Erased entire disk (including any previous data)
- Created 4 partitions in GPT layout
- Windows will consume partitions 1 + 2 (EFI + NTFS)
- Ubuntu will consume partitions 3 + 4 (ext4 + swap)

**Important:** Note the device name (`/dev/sda` or `/dev/nvme0n1`). You'll need it for next steps.

## Step 2: Boot Target Disk from USB and Install Windows

1. **Physically connect the target disk to the target machine** (or if it's internal, ensure it's the only disk)
2. **Plug in Ventoy USB** (or Windows-only USB if using Option B from Step 0)
3. **Reboot target machine, press boot menu key (F12, F9, Esc, etc.)**
4. **Select Ventoy USB from boot menu**
5. **At Ventoy boot screen, select `windows-11.iso`**

Windows installer will boot:
```
Windows 11 Setup

Where do you want to install Windows?
[Unallocated space]
├─ Partition 1: EFI System (260 MB) — Windows will use
├─ Partition 2: Reserved for Windows (256 GB) — Windows will use/format as NTFS
└─ [Select Partition 2 or unallocated space]
```

6. **Select Partition 2** (or unallocated 256 GB space)
7. **Follow Windows installer prompts:**
   - Format as NTFS (if needed)
   - Complete installation
   - Reboot when prompted

**Expected outcome:** Windows boots from the hard disk (GRUB menu not yet visible; Windows bootloader is in control).

## Step 3: Boot Ubuntu Live USB and Partition/Install

Windows installation finished, but it overwrote the GRUB bootloader. Now install Ubuntu.

1. **Plug in Ventoy USB** (or Ubuntu-only USB)
2. **Reboot target machine**
3. **Press boot menu key, select Ventoy USB**
4. **At Ventoy boot screen, select `ubuntu-24.04.iso`**

Ubuntu live environment boots:
```
Ubuntu 24.04 LTS Live

Try Ubuntu or Install
```

5. **Click "Install Ubuntu"**
6. **Follow installer prompts:**
   - Select keyboard, language, location
   - **At "Installation type" → "Custom"** (important!)
   - **Select the unallocated space / Partition 3** (256 GB Linux partition)
   - Installer will create ext4 `/` and use Partition 4 as swap
   - Proceed with installation
7. **Reboot when prompted**

**Expected outcome:** After reboot, GRUB bootloader appears with Windows and Ubuntu options.

If GRUB doesn't appear (Windows boots directly), proceed to Step 4.

## Step 4: Repair Boot (If Windows Bypasses GRUB)

Windows may overwrite GRUB bootloader during installation. If you don't see GRUB menu at startup, repair it:

### Option A: Use sysinstall (Recommended if you have a Linux machine with target disk)
On a machine where sysinstall can access the target disk:

```bash
# Connect target disk via external USB adapter or second machine
sudo sysinstall boot repair --confirm
```

### Option B: Manual Repair from Ubuntu Live USB
1. **Plug in Ventoy USB with Ubuntu ISO**
2. **Boot into Ubuntu live environment** (don't install, just live)
3. **Open terminal (Ctrl+Alt+T)**
4. **Identify target disk:**
   ```bash
   lsblk
   # Output:
   # sda     — Your target disk (512 GB)
   # sda1    — EFI System (260 MB)
   # sda2    — Windows (256 GB)
   # sda3    — Ubuntu / (256 GB)
   # sda4    — Swap (8 GB)
   ```

5. **Mount target root filesystem:**
   ```bash
   sudo mount /dev/sda3 /mnt
   sudo mount /dev/sda1 /mnt/boot/efi
   ```

6. **Mount virtual filesystems:**
   ```bash
   for dir in proc sys dev run; do
     sudo mount --rbind /$dir /mnt/$dir
   done
   ```

7. **Chroot into target system:**
   ```bash
   sudo chroot /mnt /bin/bash
   ```

8. **Reinstall GRUB:**
   ```bash
   grub-install --target=x86_64-efi --efi-directory=/boot/efi --bootloader-id=grub
   ```

9. **Update GRUB to detect Windows:**
   ```bash
   update-grub
   # Output will include: "Found Windows Boot Manager..."
   ```

10. **Exit chroot and reboot:**
    ```bash
    exit
    sudo reboot
    ```

**Expected outcome:** GRUB menu appears with both Windows and Ubuntu options.

## Step 5: Boot into GRUB Menu and Verify Both OSs

Reboot target machine. You should see:

```
╔══════════════════════════════════════════╗
║       GRUB Bootloader (orange menu)      ║
║                                          ║
║  Ubuntu (highlighted)                    ║
║  Ubuntu (recovery mode)                  ║
║  Windows Boot Manager                    ║
║                                          ║
║  Use arrow keys and Enter to select      ║
╚══════════════════════════════════════════╝
```

### Test Ubuntu Boot
1. **Keep selection on "Ubuntu"**
2. **Press Enter**
3. **Ubuntu boots, logs in, verifies it works**
4. **Reboot: `sudo reboot`**

### Test Windows Boot
1. **At GRUB menu, select "Windows Boot Manager"**
2. **Press Enter**
3. **Windows boots, logs in, verifies it works**
4. **Reboot via Windows shutdown**

Both OSs working → **Dual-boot successful!**

## Step 6: Final Verification

Boot into each OS and verify:

### Ubuntu checks:
```bash
# Check disk layout
lsblk

# Verify Windows partition is visible (not mounted)
df -h | grep -v sda

# Verify swap is active
swapon --show
```

### Windows checks:
```powershell
# Open File Explorer
# Check C: drive is Windows partition
# Check D: (if assigned) is Ubuntu partition (appears as empty NTFS)
```

## Troubleshooting

### GRUB menu not appearing (Windows boots directly)
See Step 4: Repair Boot.

### Ubuntu installer doesn't see Windows partitions
This is OK; Windows is already installed. Ubuntu installer just needs the unallocated space.

### "No such device" error in GRUB
GRUB lost access to UUID. Fix from Ubuntu live USB (Step 4, Option B).

### Black screen after selecting Ubuntu
Usually slow disk. Wait 30 seconds. If still black, try Ubuntu recovery mode from GRUB.

### Windows won't boot from GRUB
Run `update-grub` from Ubuntu again (Step 4, Option B, step 9).

### Swap partition not recognized during Ubuntu install
Can manually create in custom partitioning. Select Partition 4 as "swap area".

## Tips & Tricks

### Set Default Boot OS
To make Ubuntu boot by default (instead of GRUB menu), edit `/etc/default/grub` in Ubuntu:

```bash
sudo nano /etc/default/grub
# Find: GRUB_DEFAULT=0
# Change to: GRUB_DEFAULT=0  (Ubuntu is option 0; Windows is option 2)
# Save: Ctrl+O, Enter, Ctrl+X

# Update GRUB
sudo update-grub

# Reboot; Ubuntu boots automatically
```

### Dual-Boot Timeout
To show GRUB menu for 5 seconds before auto-booting:

```bash
sudo nano /etc/default/grub
# Find: GRUB_TIMEOUT=10
# Ensure visible (not commented out)
# Save and run: sudo update-grub
```

### Remove One OS
To remove Windows and keep Ubuntu-only:

```bash
# From Ubuntu, delete Windows partition (be careful!)
sudo parted /dev/sda rm 2  # Remove partition 2 (Windows)
```

To remove Ubuntu and keep Windows-only:

```bash
# Boot into Windows
# Disk Management → Delete partitions 3 + 4
# Delete GRUB bootloader (Windows takes over)
```

## Next Steps
- Use dual-boot system normally
- See `troubleshooting.md` if issues arise
- See `safety.md` for understanding safety gates

## Time Estimate
- Step 1 (Partitioning): 5 minutes
- Step 2 (Windows install): 20-40 minutes
- Step 3 (Ubuntu install): 20-40 minutes
- Step 4 (Boot repair, if needed): 10 minutes
- **Total: 60-100 minutes** (mostly automated; you just follow prompts)

## Common Mistakes to Avoid
1. **Selecting wrong disk in installer** — Verify device ID matches
2. **Selecting wrong partition for Windows** — Choose the 256 GB empty partition, not EFI
3. **Selecting wrong partition for Ubuntu** — Choose the unallocated 256 GB, not Windows partition
4. **Rebooting during installation** — Let installer finish fully
5. **Forgetting to repair GRUB** — If Windows overwrites bootloader, follow Step 4

## Success Indicators
- GRUB menu appears on boot
- Both Windows and Ubuntu boot successfully
- Can swap between OSs via reboot + GRUB selection
- Both OSs can see their own partitions
- Swap space active in Ubuntu
