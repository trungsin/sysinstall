# Project Changelog

All notable changes to sysinstall are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.0.1] - 2026-04-28

### Added
Initial MVP scaffold. All core functionality implemented across 9 phases.

**Phase 01: Project Scaffolding**
- Typer CLI framework with 4 command groups: `disk`, `usb`, `iso`, `boot`
- PyInstaller spec for single-binary packaging
- Cross-platform Python 3.12+ setup with `pyproject.toml`

**Phase 02: Disk Enumeration**
- Abstract `DiskEnumerator` interface with platform-specific implementations
- Windows: WMI + diskpart wrapper for disk listing
- macOS: diskutil + plistlib for disk and EFI boot enumeration
- Linux: lsblk JSON + sgdisk for disk and partition discovery
- Stable disk IDs based on serial numbers (not `/dev/sda` which can reorder)
- Encryption detection (BitLocker, FileVault, LUKS)
- Removable disk detection (USB vs internal)

**Phase 03: USB & Ventoy Installation**
- `sysinstall usb create --device <id> --confirm` for Ventoy USB creation (Windows/Linux)
- Ventoy binary download with SHA256 verification (placeholder hashes in v0.0.1)
- GPT partition table creation on USB
- Bootloader installation via Ventoy executable
- `ventoy.json` manifest creation for ISO management
- Documented limitation: macOS cannot create Ventoy USB (upstream Ventoy limitation)

**Phase 04: ISO Management**
- `sysinstall iso add <path>` to copy ISO to Ventoy USB
- `sysinstall iso remove <iso_name>` to delete ISO from USB
- `sysinstall iso list` to enumerate ISOs on connected USB
- SHA256 verification of ISO files
- Automatic `ventoy.json` update when ISOs are added/removed
- ISO mount detection (skip if already mounted)

**Phase 05: Dual-Boot Partitioning**
- `sysinstall disk partition --device <id> --layout dual-boot --confirm`
- GPT partition planner: ESP (260 MB) + Windows (configurable GB) + Linux (remaining) + Swap (8 GB)
- Partition applier using sgdisk (Linux/macOS) and diskpart (Windows)
- Backup of original partition table before applying changes
- Validation: check for overlapping partitions, ESP size, total capacity
- Optional `--dry-run` to preview partitions without applying

**Phase 06: Bootloader Repair**
- `sysinstall boot repair` (run from Ubuntu live USB) to restore GRUB after Windows installation
- Boot detector: identify current EFI boot entries and GRUB configuration
- ESP backup before repair (saved to `/root/.sysinstall/esp-backup-<timestamp>.tar`)
- EFI boot entry restoration via efibootmgr
- GRUB reinstallation via chroot into target disk + grub-install
- Mounted filesystem detection and optional auto-unmount (`--auto-unmount`)
- BitLocker post-repair warning (inform user about recovery keys)

**Phase 07: Safety Layer**
- 4 safety gates preventing dangerous operations:
  1. **System Disk Gate** (NEVER overridable) — refuse to partition/format system/boot disk
  2. **Encryption Gate** (`--force-encrypted`) — warn before touching encrypted disks
  3. **Fixed Disk Gate** (`--allow-fixed-disk`) — warn before internal (non-removable) disks
  4. **Mounted Gate** (`--auto-unmount`) — refuse if partitions mounted; allow auto-unmount
- Red-banner confirmation prompts with human-readable device details
- `--dry-run` support for all destructive operations
- Audit logging: operations logged to `~/.sysinstall/audit.log` (platform-specific)
- Log rotation: 100 MB per file, keep 5 rotated files

**Phase 08: Testing**
- 454 unit tests with mocked I/O
- Coverage gates: ≥80% for core modules, ≥60% for platform-conditional
- VM smoke test harness: Windows 11 + Ubuntu 24.04 guests
- CI workflow (`.github/workflows/ci.yml`): lint + test on Windows/macOS/Linux
- pytest markers: smoke, integration, slow for selective test runs

**Phase 09: Documentation & Packaging**
- Comprehensive documentation in `./docs/`:
  - `project-overview-pdr.md` — what, why, architecture, constraints
  - `code-standards.md` — file naming, size limits, ruff/mypy config, KISS/YAGNI/DRY
  - `codebase-summary.md` — module map, design patterns, entry points
  - `design-guidelines.md` — CLI conventions, flags, output modes, error messages
  - `deployment-guide.md` — release process, CI matrix, signing (unsigned MVP)
  - `system-architecture.md` — C4 diagrams, sequence diagrams (Mermaid)
  - `development-roadmap.md` — phase status, v0.1+ backlog, milestones
  - Per-OS install guides: `install/[windows|macos|linux].md`
  - Tutorials: `tutorials/multiboot-usb.md`, `tutorials/dual-boot-windows-ubuntu.md`
  - `troubleshooting.md` — common errors and fixes
  - `safety.md` — explicit gate catalog and audit log details
- PyInstaller spec (`sysinstall.spec`) — onefile binary, arm64 macOS
- CI release workflow (`.github/workflows/release.yml`):
  - Builds on windows-latest, ubuntu-22.04, macos-14 (arm64 only)
  - Produces signed binaries (conditional, no-op if secrets absent)
  - Creates GitHub Release with artifacts + SHA256 checksums
- Signing scripts (stubs): `scripts/sign-windows.ps1`, `scripts/sign-and-notarize-macos.sh`
- Updated `README.md` with TL;DR, install links, quick examples
- Enhanced `pyproject.toml`: description, license, keywords, classifiers, project URLs

### Known Limitations
- **macOS USB creation:** Ventoy has no macOS support; users must create USB on Linux/Windows or use `dd` with pre-built image (documented workaround)
- **Unsigned binaries:** Code signing requires paid certificates (~$400 Windows + $99 Apple); MVP ships unsigned with documented SmartScreen/Gatekeeper bypass
- **No persistence files:** Ventoy `.dat` files (persistent volumes) deferred to v0.2 (YAGNI)
- **UEFI only:** No BIOS-mode dual-boot (legacy MBR); UEFI is modern standard
- **macOS arm64 only:** Intel macOS builds dropped per decision #3 & #10; no Universal2 binary yet
- **Minimum macOS 12 Monterey:** MACOSX_DEPLOYMENT_TARGET=12; older machines unsupported

### Security
- Audit logging captures all destructive operations (timestamp, user, device, command, result)
- System disk gate prevents accidental data wipe
- No hardcoded secrets; all signing certificates via GitHub Actions secrets
- SHA256 verification of downloaded Ventoy binary and ISO files
- Input validation on device IDs (checked against enumerated disks)

### Testing
- Unit test coverage: 92.44% overall (454 tests)
- Strict coverage gates: ≥80% for pure-logic modules
- Relaxed coverage gates: ≥60% for platform-conditional modules
- VM smoke tests: Windows 11 + Ubuntu 24.04 end-to-end workflows

### Performance
- Single binary ~30 MB (arm64 macOS, Linux x64); Windows exe similar
- Cold-start latency <1s on modern hardware
- Disk enumeration uses native tools (diskpart, lsblk, diskutil) for accuracy

### Build & Packaging
- PyInstaller produces per-platform binaries (no cross-compilation)
- CI matrix: Windows, macOS arm64, Linux — all in `.github/workflows/release.yml`
- Signing conditional on GitHub Actions secrets (Windows signtool, macOS notarytool)
- SHA256 checksums generated for all artifacts

## [Unreleased]

### Planned for v0.1.0
- Code signing integration (Windows EV cert, Apple Developer Program)
- Performance profiling and optimization
- macOS USB-create workaround documentation (pre-built Ventoy image)
- Enhanced error messages with recovery suggestions

### Planned for v0.2.0
- Persistence file management (Ventoy `.dat` UI)
- BIOS-mode dual-boot support (legacy MBR)
- LUKS-encrypted root support in boot repair
- Resumable downloads

### Planned for v1.0.0
- Stable API guarantees (semantic versioning)
- GPG-signed releases
- Universal2 macOS binary (arm64 + Intel)
- Community contribution guide and governance

---

## Deprecated Features
None yet (v0.0.1 is initial release).

## Security Advisories
None yet.

## Contributors
sysinstall is maintained by the core team. See `docs/deployment-guide.md` for release procedures.
