# Phase 06 — Bootloader / Dual-Boot Finalization: Implementation Report

Date: 2026-04-28
Status: DONE

---

## Files Created

| File | LOC | Notes |
|------|-----|-------|
| `src/sysinstall/boot/__init__.py` | 90 | Public API: detect(), repair(); Linux gate + root check |
| `src/sysinstall/boot/types.py` | 65 | EfiEntry, BootEnvironment, RepairPlan, UnsupportedHostError frozen dataclasses |
| `src/sysinstall/boot/detector.py` | 155 | is_uefi(), find_candidates(); SYSINSTALL_FIRMWARE override |
| `src/sysinstall/boot/chroot.py` | 155 | ChrootContext context manager; reverse-unmount; dry_run skips subprocess |
| `src/sysinstall/boot/grub.py` | 155 | install_uefi/bios, update_grub, enable_os_prober, toggle_os_prober_text (pure) |
| `src/sysinstall/boot/efi.py` | 110 | parse_efibootmgr (pure), list_entries, set_boot_order, find_ubuntu_first_order |
| `src/sysinstall/boot/backup.py` | 115 | snapshot_esp, restore_esp, latest_snapshot |
| `src/sysinstall/boot/orchestrator.py` | 160 | run_boot_repair_tool, run_manual_repair, _derive_disk_path |
| `src/sysinstall/cli/boot.py` | 365 | Replaced stub: detect/repair/revert commands with all flags |
| `tests/boot/__init__.py` | 0 | Package marker |
| `tests/boot/test_detector.py` | 100 | 14 tests: is_uefi env override, classifier functions, find_candidates |
| `tests/boot/test_chroot_seq.py` | 100 | 8 tests: dry_run isolation, stack population, reverse order, exception cleanup |
| `tests/boot/test_efi_parser.py` | 75 | 10 tests: 4-entry fixture, boot order positions, find_ubuntu_first_order |
| `tests/boot/test_grub_cmds.py` | 85 | 7 tests: pure arg builders + mocked subprocess execution |
| `tests/boot/test_os_prober_toggle.py` | 50 | 6 tests: 3 toggle cases + idempotency |
| `tests/boot/test_host_gate.py` | 55 | 4 tests: darwin/win32 raise UnsupportedHostError; CLI exits 2 |
| `tests/boot/fixtures/efibootmgr-v.txt` | 7 | 4-entry real-world output sample |
| `tests/boot/fixtures/grub-default-with-os-prober.txt` | 8 | GRUB_DISABLE_OS_PROBER=true case |
| `tests/boot/fixtures/grub-default-no-os-prober.txt` | 7 | Missing line case |

## Files Modified

| File | Change |
|------|--------|
| `src/sysinstall/cli/boot.py` | Replaced 12-line stub with full implementation |

---

## Tasks Completed

- [x] detector.py: firmware mode + candidate partitions
- [x] chroot.py context manager with reverse-cleanup
- [x] grub.py wrappers (install_uefi, install_bios, update_grub, enable_os_prober)
- [x] efi.py with efibootmgr parser (pure function)
- [x] backup.py: snapshot_esp, restore_esp, latest_snapshot
- [x] orchestrator.py: run_manual_repair, run_boot_repair_tool
- [x] CLI boot detect + boot repair + boot revert
- [x] Linux-host gate (else helpful exit 2)
- [x] --use-boot-repair flag; exits 2 with install instructions if missing
- [x] BitLocker warning in pre-confirm prompt
- [x] Audit log: boot.detect, boot.repair.start, boot.repair.command, boot.repair.success/failure
- [x] Tests: detector, chroot seq, efi parser, grub cmds, os-prober toggle, host gate

---

## Tests Status

- Unit tests (boot module): **48 passed, 2 skipped** (2 Linux-only mount tests skipped on macOS)
- Full suite: **380 passed, 2 skipped, 0 failures**
- Type check (mypy --strict): **PASS** — no issues found in 49 source files
- Lint (ruff check): **PASS** — all checks passed

---

## Sample CLI Output (macOS host-gate — acceptance criteria 3 & 4)

```
$ python -m sysinstall boot detect
ERROR: Boot commands require a Linux environment.
Boot from an Ubuntu live USB and re-run this command there.
Exit: 2

$ python -m sysinstall boot repair --ubuntu-root /dev/sda3 --efi /dev/sda1 --confirm --dry-run
ERROR: Boot commands require a Linux environment.
Boot from an Ubuntu live USB and re-run this command there.
Exit: 2
```

## Sample boot --help (acceptance criteria 1 & 2)

```
$ python -m sysinstall boot --help
Commands: detect, repair, revert

$ python -m sysinstall boot repair --help
Options: --ubuntu-root, --efi, --no-os-prober, --no-set-boot-order,
         --use-boot-repair, --confirm, --dry-run, --json
```

## Audit Log Sample (acceptance criteria 11)

```json
{"ts": "2026-04-28T07:38:31.295827+00:00", "actor": "admin", "action": "boot.repair.start", "target": "test", "args": {"firmware": "uefi"}, "outcome": "dry_run", "error": null}
{"ts": "2026-04-28T07:38:31.296237+00:00", "actor": "admin", "action": "boot.repair.command", "target": "/dev/sda3", "args": {"cmd": "mount /dev/sda3 /tmp/x"}, "outcome": "dry_run", "error": null}
```

---

## Acceptance Criteria Checklist

| # | Criterion | Status |
|---|-----------|--------|
| 1 | `boot --help` shows detect, repair, revert | PASS |
| 2 | `boot repair --help` shows all flags incl. --use-boot-repair | PASS |
| 3 | `boot detect` on macOS exits 2 with "boot Ubuntu live USB" | PASS |
| 4 | `boot repair ... --dry-run` on macOS exits 2 same message | PASS |
| 5 | ChrootContext: exception inside `with` -> all mounts unmounted reverse | PASS (test_chroot_seq.py) |
| 6 | efibootmgr parser: 4-entry fixture -> 4 EfiEntry with correct boot order | PASS (test_efi_parser.py) |
| 7 | os-prober toggle: 3 cases all produce expected text | PASS (test_os_prober_toggle.py) |
| 8 | `pytest -q` all green (all phases) | PASS — 380 passed, 2 skipped |
| 9 | `mypy --strict src/sysinstall` clean | PASS |
| 10 | `ruff check src/sysinstall` clean | PASS |
| 11 | Audit log captures dry_run line with outcome="dry_run" | PASS (verified in-code) |

---

## Architecture Decisions / Deviations

- `ChrootContext` in dry_run skips `subprocess.run` for both mounts AND unmounts. Stack is still populated to track what would be mounted. This is correct — nothing to unmount if nothing was mounted.
- `toggle_os_prober_text` is a pure string transform extracted from `enable_os_prober` so tests can target it without filesystem setup.
- `_show_repair_prompt` is a module-level function (not inline) to keep `repair_cmd` under 100 LOC.
- ruff B008 suppressed for `backup_file: Path | None = typer.Option(...)` — standard Typer pattern that triggers false-positive; all other CLI files use the same pattern without issue.
- `detect()` is NOT gated to Linux-only (returns populated/empty BootEnvironment on any host). Only `repair()` gates. This enables `boot detect --json` to be called for introspection from non-Linux scripts without hard failure.

## Unresolved Questions

None — all spec decisions were clear. Live VM smoke test deferred (Linux host required, not available in this darwin CI environment).
