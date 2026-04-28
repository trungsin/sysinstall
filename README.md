# sysinstall

Cross-platform CLI for creating multi-boot USB drives (Ventoy) and safely setting up Windows + Ubuntu dual-boot systems.

[![CI](https://github.com/USER/sysinstall/actions/workflows/ci.yml/badge.svg)](https://github.com/USER/sysinstall/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-92%25-brightgreen)](https://github.com/USER/sysinstall)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Quick Install

### Windows
```powershell
# Download from GitHub Releases
Invoke-WebRequest -Uri "https://github.com/USER/sysinstall/releases/download/v0.0.1/sysinstall-windows-x64.exe" -OutFile sysinstall.exe
.\sysinstall.exe --version
```

### macOS (Apple Silicon)
```bash
# Download from GitHub Releases
curl -L "https://github.com/USER/sysinstall/releases/download/v0.0.1/sysinstall-macos-arm64" -o sysinstall
chmod +x sysinstall
xattr -d com.apple.quarantine sysinstall
./sysinstall --version
```

### Linux
```bash
# Download from GitHub Releases
wget https://github.com/USER/sysinstall/releases/download/v0.0.1/sysinstall-linux-x64
chmod +x sysinstall-linux-x64
./sysinstall-linux-x64 --version
```

## 60-Second Example: Multi-Boot USB

Create a Ventoy USB with Windows and Ubuntu ISOs:

```bash
# List disks (identify your USB)
sysinstall disk list

# Create Ventoy bootloader on USB (replace d1 with your USB ID)
sysinstall usb create --device d1 --confirm

# Add ISOs
sysinstall iso add ~/Downloads/windows-11.iso
sysinstall iso add ~/Downloads/ubuntu-24.04.iso

# Boot from USB, select ISO from menu, install OS
```

Done. Your USB now boots multiple operating systems.

## Dual-Boot in 5 Steps

Set up Windows + Ubuntu on a single disk:

1. **Partition disk** for dual-boot layout:
   ```bash
   sysinstall disk partition --device <disk-id> --layout dual-boot --confirm
   ```

2. **Boot Windows installer** from Ventoy USB, install to first partition

3. **Boot Ubuntu installer** from Ventoy USB, install to remaining space

4. **Boot Ubuntu live USB** and repair GRUB bootloader (if Windows overwrites it):
   ```bash
   sysinstall boot repair --confirm
   ```

5. **Reboot** and select Windows or Ubuntu from GRUB menu

See `docs/tutorials/dual-boot-windows-ubuntu.md` for detailed walkthrough.

## Safety Promise

sysinstall will never:
- Partition your system disk (strict refusal; no override)
- Touch mounted filesystems without `--auto-unmount`
- Proceed without explicit confirmation (red banners + `--confirm` flag)
- Skip audit logging (every operation logged to `~/.sysinstall/audit.log`)

All dangerous operations are guarded by safety gates. See `docs/safety.md`.

## Documentation

- **Getting started:** `docs/install/[windows|macos|linux].md`
- **Tutorials:** `docs/tutorials/` (multiboot USB, dual-boot setup)
- **Architecture:** `docs/system-architecture.md` (Mermaid diagrams)
- **Safety guarantees:** `docs/safety.md` (4 safety gates explained)
- **Troubleshooting:** `docs/troubleshooting.md` (common issues + fixes)
- **Development:** `docs/code-standards.md`, `docs/codebase-summary.md`

## Features

- **Cross-platform:** Windows, macOS (Apple Silicon), Linux
- **Ventoy USB creation:** Format USB with Ventoy bootloader (Windows/Linux only; macOS workaround documented)
- **ISO management:** Add/remove ISO files, auto-update Ventoy manifest
- **Safe partitioning:** GPT dual-boot layout with validation (ESP + Windows + Linux + Swap)
- **Boot repair:** Restore GRUB bootloader from Ubuntu live USB after Windows overwrites it
- **Audit logging:** All operations logged to `~/.sysinstall/audit.log` with rotation
- **Dry-run mode:** Preview changes without applying
- **Safety gates:** 4 layers of protection against data loss

## Requirements

- **Host OS:** Windows 10+, macOS 12+ (Apple Silicon), Ubuntu 20.04+ (or equivalent)
- **Target disk:** ≥256 GB (recommended ≥512 GB for dual-boot)
- **Privileges:** Admin/root required for disk operations
- **Python:** Not needed (single binary includes runtime)

## Known Limitations

- **macOS cannot create Ventoy USB** — Use Linux/Windows machine or `dd` workaround (see docs/install/macos.md)
- **UEFI only** — No BIOS-mode dual-boot (legacy MBR unsupported)
- **No persistence files** — Ventoy `.dat` files deferred to v0.2
- **Binaries unsigned** — SmartScreen/Gatekeeper warnings on first run (documented bypass)

## Roadmap

### v0.1.0 (Q2 2026)
- Code signing (Windows + macOS)
- Performance optimization
- Enhanced error messages

### v0.2.0 (Q3 2026)
- Persistence file management
- BIOS-mode dual-boot support
- LUKS-encrypted root in boot repair

### v1.0.0 (Q4 2026)
- Stable API (semantic versioning)
- GPG-signed releases
- Universal2 macOS binary

See `docs/development-roadmap.md` for detailed backlog.

## Support

- **Issues:** [GitHub Issues](https://github.com/USER/sysinstall/issues)
- **Discussions:** [GitHub Discussions](https://github.com/USER/sysinstall/discussions)
- **Docs:** Full documentation in `docs/` directory

## License

MIT License — See LICENSE file for details.

## Credits

sysinstall MVP built 2026-04-28 across 9 phases:
- Disk enumeration abstraction
- Ventoy USB creation (Windows/Linux)
- Partition planning + application
- GRUB bootloader repair
- Safety gates + audit logging
- Comprehensive testing (454 unit tests)
- Full documentation + CI/CD

Built for users who want safe, automated dual-boot setup without manual `fdisk`/`efibootmgr` commands.
