# Phase 05 — Hard Drive Partitioning for Dual-Boot

**Status**: pending
**Effort**: 2d
**Owner**: TBD
**Blocked by**: Phase 02

## Context Links
- Plan: [../plan.md](./plan.md)
- Research: `research/researcher-03-windows-disk-ops.md`, `-04`, `-05`

## Overview
Carve a target HDD/SSD into the GPT layout dual-boot expects: ESP + MSR + Windows + Linux root + (optional) swap. Partitions get filesystems where possible per-platform; ext4 deferred to Ubuntu installer when host can't create it.

## Key Insights
- Stable layout for UEFI dual-boot: ESP(512MB FAT32) + MSR(16MB) + Win(NTFS) + Linux ext4 + swap(opt).
- Linux host: full layout possible (sgdisk + mkfs.{fat,ntfs,ext4}).
- Windows host: can create #1–3 fully; reserve #4–5 as unallocated (mkfs.ext4 not native to Win).
- macOS host: can create GPT layout via `diskutil`/`gpt`/`newfs_*`; ext4 unsupported. Reserve unallocated for Ubuntu installer.
- **System-disk refusal is mandatory** — sysinstall never partitions the boot disk.
- Layout is "locked": MVP doesn't do shrink-existing-Windows-partition (huge can-of-worms; user does that in Windows Disk Management first or via Ubuntu installer).

## Requirements
### Functional
- `sysinstall disk partition --device <id> --layout dual-boot --windows-size <GB> [--swap-size <GB>] [--no-swap] [--dry-run] [--confirm]`.
- Validate target disk is NOT system disk.
- Show planned layout BEFORE confirm — table with partition / size / fs / mountable-by.
- Execute via platform tooling.
- `--dry-run` prints commands without running.
- Output JSON of resulting partition table for downstream phase 06.

### Non-Functional
- Plan computation pure (testable without subprocess).
- Idempotent abort: if any step fails after wipe, disk left in known-empty state (no half-formatted slices).

## Architecture

```
src/sysinstall/partition/
├── __init__.py              # public: plan(), apply()
├── layout.py                # DualBootLayout dataclass + validation
├── planner.py               # disk + opts → list[PlannedPartition]
├── runner_linux.py          # sgdisk + mkfs
├── runner_macos.py          # diskutil eraseDisk + gpt + newfs_*
└── runner_windows.py        # PowerShell Clear-Disk + New-Partition
```

```python
@dataclass(frozen=True)
class PlannedPartition:
    index: int
    label: str
    size_mb: int | None      # None = remaining
    fs: Literal["fat32","ntfs","ext4","swap","unallocated"]
    type_guid: str           # GPT type GUID
    mountpoint_hint: str | None  # e.g. "/boot/efi"

@dataclass(frozen=True)
class PartitionPlan:
    disk: Disk
    partitions: tuple[PlannedPartition, ...]
    total_required_mb: int
```

## Layout (UEFI dual-boot, GPT)

| # | Label | Size | FS | GPT GUID | Created by host? |
|---|-------|------|----|----------|------------------|
| 1 | EFI | 512 MB | FAT32 | C12A7328-... | yes (all hosts) |
| 2 | MSR | 16 MB | none | E3C9E316-... | yes (all hosts) |
| 3 | Windows | user (default 100GB) | NTFS | EBD0A0A2-... | yes (all hosts) |
| 4 | Ubuntu | remaining minus swap | ext4 OR unallocated | 0FC63DAF-... | Linux host only |
| 5 | swap (opt) | user (default 4GB) | swap OR unallocated | 0657FD6D-... | Linux host only |

When host can't format ext4/swap (Win/macOS), partition is left unallocated with correct GPT type GUID — Ubuntu installer recognizes intent and offers to format.

## Related Code Files
**Create**:
- `src/sysinstall/partition/{__init__.py,layout.py,planner.py,runner_linux.py,runner_macos.py,runner_windows.py}`
- `src/sysinstall/cli/disk.py` — extend with `partition` subcommand
- `tests/partition/test_planner.py`
- `tests/partition/test_runner_linux_cmd_gen.py`
- `tests/partition/test_runner_windows_cmd_gen.py`

**Modify**:
- `src/sysinstall/cli/__init__.py` — already wired in phase 02, just add subcommand.

## Implementation Steps

1. `layout.py` — `DualBootLayout` dataclass with validators (Windows ≥30GB, swap ≤32GB).
2. `planner.py` — `plan(disk, layout) -> PartitionPlan`. Pure function. Asserts plan fits on disk.
3. Runners produce shell command lists from PartitionPlan (testable separately from execution).
4. `runner_linux.py` — emit `sgdisk` invocations + `mkfs.fat`/`mkfs.ntfs`/`mkfs.ext4`/`mkswap`. After table change: `partprobe` + `udevadm settle`.
5. `runner_macos.py` — emit `diskutil unmountDisk`, `diskutil eraseDisk`, then `gpt add` for additional slices. Skip ext4 step (leave unallocated).
6. `runner_windows.py` — emit PowerShell script: `Clear-Disk`, `Initialize-Disk -PartitionStyle GPT`, `New-Partition` per slice with explicit `-GptType "{GUID}"`.
7. `__init__.py` — `apply(plan, dry_run=False)`. Pre-checks (system-disk, BitLocker, mounted partitions). Dispatch to runner. Streams progress.
8. CLI: `disk partition` shows planned table → confirm → execute.
9. Tests: planner table-driven; runner cmd-generation tests assert exact arg lists.

## Todo
- [ ] DualBootLayout dataclass + validators
- [ ] Pure planner function
- [ ] Linux runner (sgdisk + mkfs chain)
- [ ] Windows runner (PowerShell Storage cmdlets)
- [ ] macOS runner (diskutil + gpt)
- [ ] CLI `disk partition` with dry-run
- [ ] Pre-flight checks (system, BitLocker, mounts)
- [ ] Unit tests for planner + runners
- [ ] VM smoke (Linux, Windows hosts)

## Success Criteria
- Plan output matches table above for default opts on 500GB disk.
- Linux host: post-apply, `lsblk` shows 4–5 partitions with correct sizes + types.
- Windows host: post-apply, `Get-Partition` shows ESP/MSR/Win formatted; remaining unallocated.
- macOS host: post-apply, `gpt show` shows correct slices; non-system disk only.
- `--dry-run` prints commands; no disk changes.
- Refuses system disk every time.

## Risks
| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Wrong disk wiped | Low (with safety) | Catastrophic | Phase 07 system-disk refusal; serial-based ID; mandatory `--confirm`; show model+serial in prompt |
| Partial failure mid-format | Med | Med | Wipe-first ordering; on fail, log + advise re-run from clean |
| BitLocker on target disk | Med | High | Pre-check `Get-BitLockerVolume`; refuse if encrypted unless `--force` |
| Disk in use (mounted) | High | Low | Auto-unmount with warning |
| Sector alignment off | Low | Med | Use sgdisk/PowerShell defaults (1MiB align) |
| sgdisk missing on host | Med | Low | Detect early, instruct `apt install gdisk` |

## Security Considerations
- All disk paths validated.
- Confirm prompt shows: model + serial + size + planned ops, NOT just `/dev/sdX`.
- BitLocker / FileVault detection — refuse if encrypted (data loss risk).
- Audit log of every command emitted (phase 07).

## Test Matrix
| Test | Where |
|------|-------|
| Planner: layout fits | unit |
| Planner: layout too large → error | unit |
| Linux cmd-gen: exact sgdisk args | unit |
| Windows cmd-gen: exact PowerShell script | unit |
| macOS cmd-gen: exact diskutil/gpt args | unit |
| End-to-end Linux | VM (Ubuntu host) |
| End-to-end Windows | VM (Win11 host) |

## File Ownership (parallel-safe with phase 03/04)
- `src/sysinstall/partition/*` — this phase only
- `src/sysinstall/cli/disk.py` — extends; phase 02 owns existing commands; **add only** `partition` here

## Rollback
Destructive — once disk wiped, no in-tool recovery. Document: "back up first" in big red text in prompt + docs.

For code: revert phase commit. Phase 06 (boot repair) is logically downstream but technically independent.

## Next Steps
Phase 06 (bootloader finalization) consumes the partition layout produced here.
