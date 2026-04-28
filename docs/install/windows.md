# Installing sysinstall on Windows

## Download Binary
1. Go to [GitHub Releases](https://github.com/USER/sysinstall/releases)
2. Download `sysinstall-windows-x64.exe` (latest version)
3. Save to a convenient location (e.g., `C:\Users\<user>\Downloads\`)

## First Run (SmartScreen Warning)
sysinstall is an unsigned binary in the MVP. Windows SmartScreen may warn you:

```
Windows Defender SmartScreen prevented an unrecognized app from starting
```

**To proceed:**
1. Click "More info"
2. Click "Run anyway"
3. Windows will launch sysinstall

This warning appears only once per version; subsequent runs are quicker.

## Verify Installation
Open PowerShell and test:

```powershell
# Navigate to download folder
cd C:\Users\<user>\Downloads

# Check version
.\sysinstall.exe --version
# Output: sysinstall 0.0.1

# List disks
.\sysinstall.exe disk list
# Output: [table of disks]
```

## Optional: Add to PATH
To run `sysinstall` from any folder without `.\`:

### Option A: Using environment variable GUI
1. Press `Win + X` → "System"
2. Click "Advanced system settings"
3. Click "Environment Variables" (bottom right)
4. Under "User variables", click "New"
5. Variable name: `PATH`
6. Variable value: `C:\Users\<user>\Downloads` (or wherever you saved sysinstall.exe)
7. Click OK, restart PowerShell

### Option B: Using PowerShell (Admin)
```powershell
# Run PowerShell as Administrator
[Environment]::SetEnvironmentVariable("PATH", "$env:PATH;C:\Users\<user>\Downloads", "User")

# Restart PowerShell, then test:
sysinstall --version
```

## Running Dual-Boot Setup
See `tutorials/dual-boot-windows-ubuntu.md` for step-by-step guide.

Quick start:
```powershell
# Plug in USB drive

# List disks (identify USB)
sysinstall disk list

# Create Ventoy USB (replace <disk-id> with actual ID)
sysinstall usb create --device <disk-id> --confirm

# Add Windows ISO
sysinstall iso add C:\path\to\windows-11.iso

# Add Ubuntu ISO
sysinstall iso add C:\path\to\ubuntu-24.04.iso

# User then boots from USB and installs OS manually
```

## Troubleshooting

### "Access Denied" or Permission Errors
sysinstall requires Admin privileges for disk operations.

**Solution:** Run PowerShell as Administrator:
1. Press `Win + X` → "Windows Terminal (Admin)" or "PowerShell (Admin)"
2. Navigate to sysinstall folder: `cd C:\Users\<user>\Downloads`
3. Run: `.\sysinstall.exe disk list`

### "Device not found"
Device ID may be wrong.

**Solution:** Re-list disks:
```powershell
.\sysinstall.exe disk list
# Verify the ID column matches your USB drive (check Size and Removable columns)
```

### Binary won't run (black screen closes immediately)
May indicate missing dependencies or incompatible OS.

**Requirements:**
- Windows 10 or later
- Administrator privileges
- No antivirus blocking execution

**Solution:**
1. Try running from PowerShell (Admin) to see error message:
   ```powershell
   .\sysinstall.exe disk list
   ```
2. If errors persist, check PowerShell output and report issue on GitHub

### "Ventoy download failed"
Network issue during Ventoy binary download.

**Solution:**
```powershell
# Retry — will use cached Ventoy if partially downloaded
.\sysinstall.exe usb create --device <disk-id> --confirm
```

## Security Notes
- Binary is unsigned; SmartScreen may flag it (expected, documented, harmless)
- Audit log saved to `%APPDATA%\sysinstall\audit.log` — review if needed
- All disk operations logged for safety auditing

## Next Steps
- Read `safety.md` to understand the 4 safety gates
- Follow `tutorials/dual-boot-windows-ubuntu.md` for complete dual-boot walkthrough
- Check `troubleshooting.md` for additional error fixes

## Support
- Issues: [GitHub Issues](https://github.com/USER/sysinstall/issues)
- Docs: [Full Documentation](../README.md)
