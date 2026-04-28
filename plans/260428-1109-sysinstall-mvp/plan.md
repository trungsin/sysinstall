---
title: "sysinstall MVP — multi-boot USB + dual-boot installer CLI"
description: "Cross-platform Python CLI for Ventoy-style multi-boot USB creation and guided Windows + Ubuntu dual-boot setup."
status: pending
priority: P1
effort: 18d
branch: main
tags: [cli, python, ventoy, dual-boot, cross-platform]
created: 2026-04-28
---

# sysinstall MVP

CLI tool: cross-platform USB multiboot (Ventoy) + guided Windows/Ubuntu dual-boot. Python, single binary via PyInstaller. Host = Win/macOS/Linux. Targets users who manually click through OS installers but want safe automated disk + bootloader handling.

## Key Constraint
**Ventoy has no macOS support.** macOS host = enumeration + dual-boot finalization only; USB creation requires Win/Linux host. See `research/researcher-01-ventoy-cli.md`.

## Phases

| # | Phase | Status | Effort | File |
|---|-------|--------|--------|------|
| 01 | Project scaffolding (Typer CLI, layout, PyInstaller spec) | pending | 1d | [phase-01](./phase-01-project-scaffolding.md) |
| 02 | Cross-platform disk enumeration abstraction | pending | 2d | [phase-02](./phase-02-disk-enumeration.md) |
| 03 | USB prep + Ventoy install (Win/Linux) | pending | 3d | [phase-03](./phase-03-usb-ventoy-install.md) |
| 04 | ISO management (add/remove/list, ventoy.json) | pending | 2d | [phase-04](./phase-04-iso-management.md) |
| 05 | Hard drive partitioning for dual-boot | pending | 2d | [phase-05](./phase-05-hdd-dual-boot-partition.md) |
| 06 | GRUB / EFI dual-boot finalization | pending | 2d | [phase-06](./phase-06-bootloader-finalization.md) |
| 07 | Safety layer (dry-run, confirm, system-disk refusal, logging) | pending | 1d | [phase-07](./phase-07-safety-layer.md) |
| 08 | Tests (unit + VM smoke) | pending | 3d | [phase-08](./phase-08-tests.md) |
| 09 | Docs + CI packaging matrix | pending | 2d | [phase-09](./phase-09-docs-packaging.md) |

## Dependency Graph

```
01 ──► 02 ──► 03 ──► 04
              │
              ├──► 05 ──► 06
              │
              └──► 07 (cross-cuts 03/05/06)

08 ──► gates merge of 03/04/05/06
09 ──► last (depends on all green)
```

Phase 07 (safety) is cross-cutting — implemented as a module from start, but its hardening checkpoint blocks each destructive phase from being declared "done".

## Research Reports
- `research/researcher-01-ventoy-cli.md` — Ventoy automation
- `research/researcher-02-disk-enumeration.md` — psutil + native tools
- `research/researcher-03-windows-disk-ops.md` — PowerShell + UAC
- `research/researcher-04-macos-disk-ops.md` — diskutil + plistlib
- `research/researcher-05-linux-disk-ops.md` — lsblk + sgdisk
- `research/researcher-06-grub-repair.md` — boot-repair / efibootmgr
- `research/researcher-07-pyinstaller-packaging.md` — CI matrix + signing

## Top Risks
| Risk | Impact | Mitigation |
|------|--------|------------|
| Wrong disk wiped | Catastrophic | Phase 07 system-disk refusal; double `--confirm`; serial-based ID |
| Ventoy macOS gap | High UX | Document workaround; macOS host shows clear "use Linux/Windows" message |
| Code signing cost (~$400/yr) | Medium | Ship unsigned MVP + docs for SmartScreen/Gatekeeper bypass |
| Partial dual-boot (Windows clobbers GRUB) | High | Phase 06 automates repair from Ubuntu live USB |

## Locked Decisions (2026-04-28)
| # | Decision | Choice |
|---|----------|--------|
| 1 | Code signing | **Unsigned MVP** — ship with documented SmartScreen/Gatekeeper bypass; revisit at v1.0 |
| 2 | macOS USB-create workaround | Document `dd` of pre-built Ventoy image (no Linux-VM guidance) |
| 3 | macOS binary | **Apple Silicon only (M1+, arm64)** — no Intel build, no Universal2 |
| 4 | Ventoy persistence files | **Defer** to v2 (YAGNI) |
| 5 | macOS minimum | **macOS 12 Monterey** |
| 6 | macOS APFS handling | Whole disks only (skip synthesized volumes) |
| 7 | BitLocker after GRUB repair | **Warn only** — print recovery-key reminder, no PCR sequencing |
| 8 | boot-repair tool | **Orchestrate existing** `boot-repair` package (no reimplementation) |
| 9 | Audit log | 100MB rotate, keep 5 files (defaults locked) |
| 10 | macOS arch target | arm64 only (`darwin/arm64` in CI matrix; drop `darwin/amd64`) |

## Success Criteria
- `sysinstall usb create --device <id> --confirm` produces bootable Ventoy USB on Win + Linux.
- `sysinstall iso add <path>` copies ISO + updates `ventoy.json`.
- `sysinstall disk partition --layout dual-boot --device <id>` produces valid GPT layout.
- `sysinstall boot repair` restores GRUB on dual-boot system from Ubuntu live USB.
- `sysinstall disk list` works on all 3 host OS.
- VM smoke tests pass on Win11 + Ubuntu 24.04 guests.
- Single binary <40 MB, runs without bundled Python.
