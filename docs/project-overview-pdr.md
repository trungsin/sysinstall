# sysinstall — Project Overview & PDR

## What
**sysinstall** is a cross-platform CLI tool for creating multi-boot USB drives (powered by Ventoy) and safely setting up Windows + Ubuntu dual-boot systems on existing machines.

### Target User
System administrators, power users, and developers who need to:
- Create bootable multi-ISO USB drives (Windows, Linux, tools) without clicking through UI wizards
- Automate the dual-boot setup process: safe disk partitioning → Windows install → Ubuntu install → GRUB repair
- Script OS deployments across lab machines or personal fleet without risk

### Core Features
- **Disk enumeration:** Unified API for listing disks on Windows, macOS, Linux
- **USB multiboot:** Automated Ventoy USB creation (Windows/Linux hosts only)
- **ISO management:** Add/remove ISO files to/from Ventoy USB, manage `ventoy.json` metadata
- **Disk partitioning:** Safe GPT layout for dual-boot (Windows + Linux) with validation
- **Bootloader repair:** GRUB restoration from Ubuntu live USB after Windows overwrites boot sector
- **Safety guards:** System disk refusal, confirmation prompts, dry-run mode, audit logging, encrypted disk detection

## Why
Manual dual-boot setup is error-prone: one typo in `fdisk` or `efibootmgr` can render a machine unbootable. Windows installers consume entire disks by default, requiring manual ESP recovery. GRUB repair requires chroot into a live USB with arcane `efibootmgr` commands.

sysinstall automates the dangerous parts, validates inputs before touching disks, and provides clear error messages when safety gates refuse operations.

## How It Works
1. User plugs in USB drive
2. `sysinstall disk list` shows available disks with human-readable names (vendor, model, capacity)
3. `sysinstall usb create --device <id> --confirm` formats USB as Ventoy bootloader
4. `sysinstall iso add windows.iso ubuntu.iso` copies ISOs to USB, updates manifests
5. User boots from USB, selects Windows installer
6. `sysinstall disk partition --layout dual-boot --device <id>` pre-creates ESP + Windows + Linux partitions
7. User installs Windows (consumes allocated partitions)
8. User installs Ubuntu from Ventoy menu into remaining space
9. `sysinstall boot repair` (from Ubuntu live USB) restores GRUB if Windows clobbered boot sector
10. User reboots into dual-boot GRUB menu

## Architecture
```
CLI (Typer)
  ├── disk        (list, partition, list-efi)
  ├── usb         (create, info)
  ├── iso         (add, remove, list)
  ├── boot        (repair, list, detect)
  └── safety      (cross-cutting gates + logging)
       │
       └── Core backend modules
            ├── disks (windows.py, macos.py, linux.py)
            ├── ventoy (manifest.py, installer.py)
            ├── partition (planner.py, applier.py)
            ├── boot (efi.py, grub.py, orchestrator.py)
            ├── iso (catalog.py, copy.py, checksum.py)
            └── safety (guards.py, audit.py, prompts.py)
```

## Constraints & Assumptions
- **Python 3.12+** — single-binary via PyInstaller
- **Ventoy not available on macOS** — USB creation limited to Windows/Linux hosts; macOS can only list disks and repair boot
- **GPT disks only** — no MBR/legacy BIOS (modern machines use UEFI)
- **Root/Admin required** — raw disk access is privileged; tool prompts for elevation where needed
- **English CLI** — error messages in English only (no i18n)

## Non-Goals (v1+)
- GUI application
- Windows ToGo or macOS multi-boot (scope limited to dual-boot setup)
- Persistent live USB (Ventoy `.dat` files) — deferred to v2
- BIOS-mode dual-boot (legacy MBR)
- Universal2 macOS binary (arm64 only in MVP; Intel dropped)
- Persistence file auto-management

## Success Metrics (MVP)
1. Single executable <40 MB, no bundled Python required
2. All platforms (Win/macOS/Linux) build from one CI matrix on tag push
3. Unit test coverage ≥80% (core modules) + ≥60% (platform-conditional)
4. VM smoke tests pass: Windows 11 + Ubuntu 24.04 guests
5. New user can create dual-boot system in <10 minutes from docs

## Roadmap Reference
See `development-roadmap.md` for phase status, current sprint, and post-MVP features.

## Plan Context
This MVP was planned over 9 phases from 2026-04-28.
- Phases 01–08: Implemented scaffold, disk enumeration, Ventoy USB, partitioning, bootloader, safety, tests
- Phase 09: Finalize docs, packaging, CI release workflow

See `/plans/260428-1109-sysinstall-mvp/` for detailed phase documentation.
