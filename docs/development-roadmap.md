# Development Roadmap

## Current Status: MVP (v0.0.1)
Shipped 2026-04-28. All 9 phases complete.

| Phase | Component | Status | Effort |
|-------|-----------|--------|--------|
| 01 | Project scaffolding (Typer CLI, layout) | DONE | 1d |
| 02 | Disk enumeration abstraction | DONE | 2d |
| 03 | USB + Ventoy install (Win/Linux) | DONE | 3d |
| 04 | ISO management | DONE | 2d |
| 05 | HDD dual-boot partitioning | DONE | 2d |
| 06 | GRUB / EFI bootloader repair | DONE | 2d |
| 07 | Safety layer (gates, audit, dry-run) | DONE | 1d |
| 08 | Tests (unit + VM smoke) | DONE | 3d |
| 09 | Docs + packaging + CI release | DONE | 2d |

## Post-MVP Backlog

### v0.1.0 (Mid-year)
Focus: Polish, signing, performance.

- [ ] **Code Signing (Windows + macOS)**
  - Acquire EV code-signing certificate for Windows (~$400/yr)
  - Acquire Apple Developer Program ($99/yr) for notarization
  - Integrate signtool + notarytool into CI
  - Test on real hardware (avoid SmartScreen/Gatekeeper warnings)
  - Effort: 2d

- [ ] **Performance Optimization**
  - Profile cold-start latency (target <500ms from CLI parse to operation)
  - Optimize disk enumeration caching (avoid repeated OS calls)
  - Lazy-load platform-specific modules
  - Effort: 2d

- [ ] **macOS USB-Create Workaround**
  - Provide pre-built Ventoy image for download
  - Document `dd` command for USB creation on macOS
  - Add integrity check (SHA256) for pre-built image
  - Effort: 1d

- [ ] **Enhanced Error Messages**
  - Provide recovery suggestions for common errors
  - Add FAQ links in error output
  - Effort: 1d

### v0.2.0 (Post-MVP, 2-3 months out)
Focus: User experience + advanced features.

- [ ] **Persistence File Management (.dat)**
  - UI to allocate persistence space on Ventoy USB
  - Auto-expand persistent volume when ISO added
  - Document LUKS encryption of persistence files
  - Effort: 3d

- [ ] **BIOS-Mode Dual-Boot (Legacy MBR)**
  - Support older machines without UEFI
  - Detect BIOS vs UEFI at boot time
  - Create MBR partition table + boot code
  - Test on legacy VirtualBox VM
  - Effort: 2d

- [ ] **Boot Repair: LUKS Root Support**
  - Detect encrypted root filesystems (LUKS)
  - Mount encrypted partitions during chroot
  - Restore GRUB with encrypted volumes
  - Effort: 2d

- [ ] **Resume Downloads**
  - Cache partial Ventoy downloads (interrupted network)
  - Verify SHA256 of partial chunks
  - Resume from byte offset
  - Effort: 2d

- [ ] **Web UI Dashboard (Opt-in)**
  - REST API over localhost:8000
  - Vue.js frontend (disk list, operation tracking, logs)
  - Real-time progress via WebSocket
  - Optional; CLI-only is still default
  - Effort: 5d (team effort)

### v1.0.0 (Stable Release, EOY)
Focus: Stability, documentation, community.

- [ ] **Stable API & Guarantees**
  - Lock CLI flags (no more renaming without deprecation warning)
  - Semantic versioning (MAJOR.MINOR.PATCH)
  - Backward compatibility guarantees
  - Effort: 1d

- [ ] **GPG-Signed Releases**
  - Generate project GPG key
  - Sign release artifacts
  - Publish fingerprint
  - Document verification
  - Effort: 1d

- [ ] **Comprehensive Test Coverage**
  - Expand VM smoke tests (BIOS mode, encrypted partitions)
  - Add integration tests for real hardware (optional)
  - Achieve ≥85% code coverage
  - Effort: 2d

- [ ] **Community Contribution Guide**
  - CONTRIBUTING.md with code style, PR template
  - Security policy (responsible disclosure)
  - Issue templates (bug, feature, question)
  - Effort: 1d

- [ ] **Universal2 macOS Binary**
  - Build arm64 + x86_64 in single fat binary
  - Test on Apple Silicon + Intel Macs
  - Keep binary size under 50 MB
  - Effort: 2d

- [ ] **Official Website**
  - Landing page with screenshots
  - Quick-start guide (link to docs)
  - FAQ + common errors
  - Effort: 2d (design + dev)

## Known Limitations & Future Ideas

### Deferred to v2+ (YAGNI)
- **Persistence file UI** — Complex workflow; defer until v0.2
- **BIOS-mode support** — Not critical for modern machines; defer
- **LUKS root in boot repair** — Edge case; defer
- **macOS Universal2** — Intel Macs are declining; arm64 only for v0.x
- **Windows Store release** — Requires signing; defer

### Upstream Dependencies
- **Ventoy 1.1.05** — Monitor releases; update when stable
- **boot-repair package** — Maintained by Ubuntu; may diverge; monitor
- **Python 3.13** — Test compatibility; don't rush upgrade

### Architectural Improvements (Future)
- **Async I/O** — Current sync I/O is fine for MVP; async if performance bottleneck
- **Plugin system** — Not needed for MVP; revisit if third-party contributions emerge
- **Config file** — `.sysinstall/config.toml` for defaults; low priority

## Milestones & Timeline

| Target | Version | Status | Features |
|--------|---------|--------|----------|
| 2026-04-28 | 0.0.1 | SHIPPED | MVP (USB, partition, boot repair) |
| 2026-06-30 | 0.1.0 | TODO | Signing, performance, macOS workaround |
| 2026-09-30 | 0.2.0 | TODO | Persistence, BIOS mode, LUKS |
| 2026-12-31 | 1.0.0 | TODO | Stable API, GPG signing, Universal2 |

## Success Metrics

### Current (MVP)
- [x] Disk enumeration works on Win/macOS/Linux
- [x] USB creation works on Win/Linux (documented macOS gap)
- [x] Partitioning works for dual-boot
- [x] Boot repair works from Ubuntu live USB
- [x] 454 unit tests + VM smoke harness pass
- [x] Coverage ≥80% (core) + ≥60% (platform-conditional)
- [x] Single binary <40 MB
- [x] All docs published

### Stretch (v0.1.0)
- [ ] Windows binary signed (SmartScreen reputation)
- [ ] macOS binary notarized (Gatekeeper cleared)
- [ ] Cold-start latency <500ms
- [ ] 100+ downloads first month
- [ ] Zero reported data-loss bugs

### Long-term (v1.0.0)
- [ ] 1000+ downloads
- [ ] Community contributions (PRs)
- [ ] Used in production labs
- [ ] Stable API (no breaking changes)

## Research Todos

### Before v0.1.0
- [ ] Acquire Windows code-signing certificate (timeline + cost)
- [ ] Validate Apple Developer Program enrollment + notarization process
- [ ] Profile disk enumeration latency on large systems (100+ disks)

### Before v0.2.0
- [ ] Research Ventoy persistence file format (`.dat` LUKS encryption)
- [ ] Test BIOS-mode boot on legacy hardware (VirtualBox BIOS VM)
- [ ] Evaluate `grub-probe` for detecting LUKS-encrypted root

## Communication & Announcements

### v0.0.1 Release Notes
```
Announcing sysinstall MVP (v0.0.1)

Multi-boot USB + dual-boot CLI for Windows and Linux.

Features:
- Cross-platform disk enumeration (Win/macOS/Linux)
- Ventoy USB creation (Win/Linux only; macOS workaround documented)
- Safe dual-boot partitioning with validation
- GRUB repair from Ubuntu live USB
- Audit logging + dry-run support
- 454 unit tests + VM smoke harness

Known Limitations:
- Binaries are unsigned (SmartScreen/Gatekeeper warnings on first run)
- macOS cannot create Ventoy USB (use Linux/Windows or dd workaround)
- No persistence file UI yet
- No BIOS-mode (UEFI only)

Get Started:
- Download binary from GitHub releases
- See install/[windows|macos|linux].md for setup
- Run: sysinstall --help

Next: v0.1.0 (code signing, performance optimization)
```

## Feedback Loops
- Monitor GitHub issues for user pain points
- Track support questions in FAQ
- Quarterly roadmap reviews with team
- Annual post-mortems on major incidents

## Contingencies
- **If code signing costs spike:** Keep unsigned MVP, document bypass, revisit at v1.0
- **If Ventoy becomes unmaintained:** Evaluate alternatives (GRUB2, syslinux); plan migration
- **If macOS support drops:** Focus on Win/Linux; sunset macOS binary support with notice
- **If test infrastructure fails:** Maintain manual smoke test SOP for releases
