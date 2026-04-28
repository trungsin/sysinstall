# Phase 03 — USB Preparation + Ventoy Install

**Status**: pending
**Effort**: 3d
**Owner**: TBD
**Blocked by**: Phase 02

## Context Links
- Plan: [../plan.md](./plan.md)
- Research: `research/researcher-01-ventoy-cli.md`, `-03`, `-05`, `-07`

## Overview
First destructive phase. Download Ventoy upstream binary per platform, run its CLI against target USB, write initial `ventoy.json`. Windows + Linux only — macOS prints unsupported message.

## Key Insights
- Ventoy 1.1.x has stable CLI flags (`-i`, `-I`, `-u` Linux; `VTOYCLI /I /U` Windows).
- Output files (`cli_done.txt`, `cli_percent.txt`) — Windows progress is file-poll, Linux is stdout tail.
- macOS: hard fail with helpful message. Document `dd`-based image flash as v2 path.
- Ventoy binary cached under `~/.cache/sysinstall/ventoy/<version>/`; checksums verified.

## Requirements
### Functional
- `sysinstall usb create --device <id> [--reserve-mb N] [--secure-boot] [--confirm]`.
- Default partition style GPT, FS exFAT (max ISO size + Win/macOS/Linux read).
- Verify SHA256 of downloaded Ventoy binary against pinned manifest.
- Refuse if `disk.is_system=True`.
- Refuse if `disk.is_removable=False` unless `--allow-fixed-disk` (still gated by `--confirm`).
- Progress bar during install (Windows: poll `cli_percent.txt`; Linux: parse stdout).
- After install, write `/ventoy/ventoy.json` to first partition with our managed-config preamble.

### Non-Functional
- Ventoy install end-to-end <60s on USB 3.0 16GB stick.
- Network download retried 3x with exponential backoff.
- Resumable download (HTTP Range) — nice-to-have, defer to v2.

## Architecture

```
src/sysinstall/ventoy/
├── __init__.py              # public: install_to_disk(), update(), is_installed()
├── downloader.py            # fetch + sha256 verify
├── manifest.py              # pinned versions + per-platform URLs/SHAs
├── runner_windows.py        # Ventoy2Disk.exe VTOYCLI invocation + progress
├── runner_linux.py          # Ventoy2Disk.sh invocation
└── config.py                # ventoy.json read/write (used heavily in phase 04)
```

```python
# manifest.py — pinned snapshot, updated on Ventoy releases
VENTOY_VERSION = "1.1.05"
ARTIFACTS = {
    "windows-x64":  ("ventoy-1.1.05-windows.zip",  "<sha256>"),
    "linux-x64":    ("ventoy-1.1.05-linux.tar.gz", "<sha256>"),
}
```

## Data Flow

```
user: sysinstall usb create --device usb:Kingston:5B86

  → resolve disk_id (phase 02)
  → safety: is_system? is_fixed and not --allow-fixed? → refuse
  → confirm prompt (or --confirm)
  → ensure ventoy binary cached + verified (downloader)
  → unmount disk's partitions
  → invoke runner_<platform>.install(disk.path)
       │
       ├─ Win: subprocess Ventoy2Disk.exe VTOYCLI /I /PhyDrive:N /GPT [/NOSB|/SecureBoot]
       │      poll cli_done.txt; report cli_percent.txt
       │
       └─ Linux: subprocess sh Ventoy2Disk.sh -I -g [/-s] /dev/sdX
                stream stdout, regex progress
  → after success: mount first partition, write skeleton ventoy.json
  → report success + path to ISOs dir
```

## Related Code Files
**Create**:
- `src/sysinstall/ventoy/{__init__.py,downloader.py,manifest.py,runner_windows.py,runner_linux.py,config.py}`
- `src/sysinstall/cli/usb.py` (replace stub)
- `src/sysinstall/safety/` (cross-cut from phase 07 — minimum viable here)
- `tests/ventoy/test_downloader.py`
- `tests/ventoy/test_runner_windows_parsing.py`
- `tests/ventoy/test_runner_linux_parsing.py`
- `tests/ventoy/fixtures/cli_done.txt`, `ventoy-linux-stdout.txt`

**Modify**:
- `src/sysinstall/cli/__init__.py` — wire usb subcommand.

## Implementation Steps

1. `manifest.py` — pinned artifact list w/ SHA256.
2. `downloader.py` — `fetch_ventoy(platform_key) -> Path`. Cache dir, atomic write, sha256 verify. Use `urllib` (stdlib) — no extra deps.
3. `config.py` — `read(usb_mount: Path) -> VentoyConfig`, `write(usb_mount, cfg)`. Pydantic-free; use stdlib `json`. Define `VentoyConfig` dataclass with `version: int`, `managed_isos: list[ManagedIso]` (sysinstall metadata in `_sysinstall` namespace key — never overwrite user-edited keys).
4. `runner_linux.py` — subprocess wrapper. Input: device path + flags. Stream stdout to logger. Parse `XX%` regex. Return rc.
5. `runner_windows.py` — subprocess Ventoy2Disk.exe. Poll `cli_percent.txt` every 250ms; on `cli_done.txt` exists, read 0/1.
6. `__init__.py` — `install_to_disk(disk: Disk, *, secure_boot, reserve_mb, dry_run)`. Dispatches to runner. Macros:
   ```python
   if sys.platform == "darwin":
       raise UnsupportedHostError(MACOS_VENTOY_MESSAGE)
   ```
7. CLI `usb create` — wires to `install_to_disk`. Confirm prompt unless `--confirm`. Pretty progress via Rich.
8. After successful install: mount first partition (platform helper), write `ventoy.json` skeleton.
9. Tests: parser tests use stdout fixtures; downloader test uses tempdir + local HTTP fixture.
10. macOS smoke: `usb create` exits 2 with macOS-not-supported message; CI assertion.

## Todo
- [ ] Manifest with pinned Ventoy version + SHAs
- [ ] Downloader + cache + verification
- [ ] Linux runner + stdout parser
- [ ] Windows runner + cli_*.txt poller
- [ ] macOS unsupported error path
- [ ] ventoy.json skeleton writer
- [ ] Mount/unmount helpers per platform
- [ ] CLI `usb create` end-to-end
- [ ] Unit tests for runners + downloader
- [ ] Integration smoke (Linux VM, Windows VM)

## Success Criteria
- On Linux VM with USB passthrough: `sysinstall usb create --device <id> --confirm` produces bootable Ventoy USB; QEMU boots into Ventoy menu.
- On Windows 11 VM: same outcome.
- On macOS: command exits with clear unsupported message + alt instruction.
- Re-run on already-Ventoy USB: detects + suggests `usb update`.

## Risks
| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Wrong disk targeted | Low (with safety) | Catastrophic | Phase 07 system-disk + fixed-disk gates; serial-based ID; double confirm |
| Ventoy CLI flag drift | Med | Med | Pin Ventoy version in manifest; `--allow-newer-ventoy` escape hatch |
| Network failure during download | Med | Low | 3x retry, resumable in v2 |
| Permission denied (no Admin/root) | High | Low | Detect early, instruct user |
| Partition not mounted after install | Med | Med | Retry mount; if fail, mount manually |

## Security Considerations
- Verify SHA256 of downloaded Ventoy binary against pinned manifest. Reject mismatch with red error.
- All `subprocess` calls use list args (no `shell=True`).
- Disk path passed through validator (`/dev/sd[a-z]`, `/dev/disk[0-9]+`, `\\.\PhysicalDrive[0-9]+`) before subprocess.
- Confirmation prompt prints model + serial + size — not just path.

## Test Matrix
| Test | Where |
|------|-------|
| Manifest sha256 verify | unit |
| Linux runner stdout parsing | unit |
| Windows cli_*.txt polling logic | unit (fixture-driven) |
| macOS unsupported exit | unit |
| End-to-end Ventoy install | VM (Linux + Windows) |

## Rollback
Destructive — once Ventoy installed, original USB contents gone. Recovery = re-flash from another source. Plan documents this; no in-tool rollback.

For code: revert phase commit; phase 04 depends on it, also revert.

## File Ownership (parallel-safe)
- `src/sysinstall/ventoy/*` — this phase only
- `src/sysinstall/cli/usb.py` — this phase only
- Shared with phase 04: `ventoy/config.py` (this phase writes skeleton; phase 04 mutates managed-iso list)

## Next Steps
Phase 04 — ISO management. Reuses `ventoy/config.py`.
