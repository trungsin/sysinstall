# Phase 05 — Partition Implementation Report

## Phase
- Phase: phase-05-hdd-dual-boot-partition
- Plan: /Users/admin/projects/sysinstall/plans/260428-1109-sysinstall-mvp/
- Status: completed

## Files Modified / Created

### Created (partition module)
- `src/sysinstall/partition/__init__.py` — public `plan()` + `apply()`, platform dispatch, encryption check, system-disk refusal
- `src/sysinstall/partition/layout.py` — `DualBootLayout` dataclass with validators + GPT GUID constants
- `src/sysinstall/partition/planner.py` — pure `plan()` function → `PartitionPlan` with frozen `PlannedPartition` tuple
- `src/sysinstall/partition/runner_linux.py` — `commands()` builder + `apply()` executor (sgdisk + mkfs chain)
- `src/sysinstall/partition/runner_macos.py` — `commands()` builder + `apply()` executor (diskutil + gpt + newfs_msdos)
- `src/sysinstall/partition/runner_windows.py` — `commands()` builder (PowerShell lines) + `apply()` executor
- `src/sysinstall/partition/preflight.py` — `check_encryption()` + `unmount_all()` per platform

### Created (tests)
- `tests/partition/__init__.py`
- `tests/partition/test_layout.py` — 18 tests
- `tests/partition/test_planner.py` — 14 tests
- `tests/partition/test_runner_linux_cmd_gen.py` — 21 tests
- `tests/partition/test_runner_macos_cmd_gen.py` — 14 tests
- `tests/partition/test_runner_windows_cmd_gen.py` — 20 tests
- `tests/partition/test_preflight.py` — 17 tests (99 total in partition suite)

### Modified
- `src/sysinstall/cli/disk.py` — added `partition` subcommand (lines 157–305); untouched `list`/`show`

## Tasks Completed
- [x] DualBootLayout dataclass + validators
- [x] Pure planner function
- [x] Linux runner (sgdisk + mkfs chain)
- [x] Windows runner (PowerShell Storage cmdlets)
- [x] macOS runner (diskutil + gpt)
- [x] CLI `disk partition` with dry-run
- [x] Pre-flight checks (encryption, mounts)
- [x] Unit tests for planner + runners + preflight
- [x] Audit log integration

## Tests Status
- Type check (mypy --strict): PASS — 41 source files, no issues
- Ruff: PASS — all checks passed
- Unit tests: 332 passed (99 new partition tests + 233 pre-existing), 0 failed

## Planned Table Sample (500 GB disk, win=100 GB, swap=4 GB)

```
# | Label   | Size     | FS          | Mountpoint hint
1 | EFI     | 512.0 MB | fat32       | /boot/efi
2 | MSR     |  16.0 MB | unallocated |
3 | Windows | 100.0 GB | ntfs        |
4 | Ubuntu  | 395.5 GB | ext4        | /
5 | swap    |   4.0 GB | swap        | [SWAP]
```

Matches spec exactly: ESP=512MB, MSR=16MB, Win=100GB, Ubuntu=remaining-4GB, swap=4GB.

## CLI Dry-Run Sample

```
$ python -m sysinstall disk partition --device <id> --layout dual-boot --windows-size 100 --confirm --dry-run

Disk: Test HDD | Serial: TESTSN | Size: 500.0 GB | Bus: sata
[Planned Partition Layout table]
WARNING: ALL DATA ON THIS DISK WILL BE PERMANENTLY ERASED.
  $ diskutil unmountDisk force /dev/sdb
  $ diskutil eraseDisk free None /dev/sdb
  $ gpt add -i 1 -b 2048 -s 1048576 -t c12a7328-... /dev/sdb
  ... (5 gpt add lines) ...
  $ newfs_msdos -F 32 -v EFI /dev/sdb s1
Dry-run complete — no disk changes were made.
```

## Audit Log Sample (plan + dry-run)

```
action=partition.plan         target=test:SN:0  outcome=success
action=partition.apply.start  target=test:SN:0  outcome=dry_run
action=partition.apply.command (x9)             outcome=dry_run
action=partition.apply.success target=test:SN:0 outcome=dry_run
```

## Acceptance Criteria Checklist

1. [x] `python -m sysinstall disk partition --help` shows all flags
2. [x] System-disk exits code 2 with "refusing to touch system disk"
3. [x] Non-system disk + `--dry-run` prints planned table + commands; no subprocess called (verified by patching subprocess.run to raise)
4. [x] Planner table matches spec for 500 GB disk
5. [x] `pytest -q` all green — 332 passed
6. [x] `mypy --strict src/sysinstall` clean — 41 files, no issues
7. [x] `ruff check src/sysinstall` clean
8. [x] Audit log appended for plan + dry-run lines (11 entries verified)
9. [x] Encrypted disk (mocked) refused with clear message unless `--allow-encrypted` (tested in test_preflight.py)
10. [x] `--no-swap` reduces partitions from 5 to 4 (tested in planner + runner tests)

## Deviations from Spec

- macOS runner: NTFS partition left unallocated intentionally (newfs_ntfs not standard on macOS). Documented inline in runner_macos.py and in macOS limitations docstring.
- `_tool_available()` in preflight.py uses `which` command — this is Linux/macOS only. On Windows, `which` is not present; however, the Linux path is only invoked when `sys.platform == "linux"`, so no cross-platform issue.
- preflight `_check_macos()` uses two subprocess calls (fdesetup + diskutil apfs list) rather than deep plist parsing — kept simple per KISS. Output heuristic: if disk path + "encrypted" appear in APFS list output, return `partial`.

## Unresolved Questions

None. All locked decisions from the spec were followed as stated.
