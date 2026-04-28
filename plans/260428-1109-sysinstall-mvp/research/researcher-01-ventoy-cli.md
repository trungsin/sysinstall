---
title: Ventoy CLI Automation Research
date: 2026-04-28
type: research-report
---

# Ventoy CLI Automation

## Verdict
Ventoy supports non-interactive CLI on **Windows + Linux only**. **macOS is NOT supported** (upstream confirmed, no plans). This is the single largest architecture constraint.

## Windows: `Ventoy2Disk.exe VTOYCLI`

Syntax: `Ventoy2Disk.exe VTOYCLI CMD DISK [Options]`

| Flag | Purpose |
|------|---------|
| `/I` | Install (force) |
| `/U` | Update existing Ventoy |
| `/Drive:X:` | Target by drive letter |
| `/PhyDrive:N` | Target by physical disk number (preferred — avoids drive letter races) |
| `/GPT` | GPT partitioning (default MBR) |
| `/NOSB` | Disable Secure Boot |
| `/NOUSBCheck` | Bypass USB validation (dangerous — allows internal disks) |
| `/R:MB` | Reserve trailing space (MB) |
| `/FS:NTFS\|EXFAT\|FAT32` | First-partition filesystem |
| `/NonDest` | Non-destructive install |

**Output files** (poll for progress/result):
- `cli_log.txt` — operation log
- `cli_percent.txt` — progress 0–100
- `cli_done.txt` — `0` success, `1` failure

**Implication**: We shell out, watch `cli_done.txt`, scrape `cli_percent.txt` for progress bar.

## Linux: `Ventoy2Disk.sh`

Syntax: `sh Ventoy2Disk.sh CMD [OPTS] /dev/sdX`

| Flag | Purpose |
|------|---------|
| `-i` | Install (fail if Ventoy already there) |
| `-I` | Force install |
| `-u` | Update |
| `-l` | List Ventoy info |
| `-r MB` | Reserve trailing space |
| `-s` | Enable Secure Boot |
| `-g` | GPT (default MBR) |
| `-L LABEL` | Custom partition label |
| `-n` | Non-destructive (with `-i`/`-I`) |

**Implication**: Requires `sudo`. Stdout is human-readable — parse exit code + tail `-l` JSON-ish output.

## macOS: NOT SUPPORTED

Confirmed: Ventoy upstream has zero macOS support, no roadmap. Apple Silicon also out.

**Workarounds for macOS host**:
1. **Ventoy LiveCD via Linux VM** — user runs Ventoy from a Linux ISO booted in UTM/Parallels. Heavy.
2. **Manual Ventoy install via raw `dd`** — pre-built Ventoy USB image flashed with `dd` to USB. Loses upgrade-in-place; full reflash each time.
3. **Defer to Linux/Windows** — sysinstall on macOS prints "USB creation requires Windows/Linux host. Run [...] there." Treat USB-creation as a *target-platform-only* feature.

**Recommendation**: For MVP, take option 3 — `sysinstall usb create` on macOS exits with clear message; macOS still gets disk-enumeration + dual-boot-finalization commands. Revisit `dd` flow in v2.

## Plugin / `ventoy.json` Config

`/ventoy/ventoy.json` on first partition — drives:
- Persistence files per-ISO (`persistence` array)
- Per-ISO boot params, theme, password, auto-install
- BIOS/UEFI mode-specific config (`control` plugin)

**Implication**: After `Ventoy2Disk` succeeds, sysinstall writes `ventoy.json` to the FAT32/exFAT first partition for our managed ISO list. ISO files copied directly to that partition root.

## Persistence Plugin

`persistence` array in `ventoy.json` maps ISO basename → backend `.dat` file. Multi-backend per ISO (boot-time menu).

For MVP: persistence is opt-in per ISO via `sysinstall iso add --persist=<size>`. Skip if YAGNI bites.

## Unresolved Questions

- Exit codes for `Ventoy2Disk.sh` (Linux) — only stdout/return-code documented; need empirical test.
- Behavior when target physical disk already mounted — does Ventoy auto-unmount? Need test.
- `/NOUSBCheck` flag risk surface — should sysinstall ever pass it? (Tentative: NO, never.)
