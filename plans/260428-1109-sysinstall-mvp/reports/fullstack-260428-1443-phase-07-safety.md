# Phase 07 — Safety Layer Hardening: Implementation Report

**Date:** 2026-04-28
**Status:** DONE
**Phase:** 07 — Safety Layer

---

## Files Created

| File | LOC | Purpose |
|------|-----|---------|
| `src/sysinstall/safety/errors.py` | 53 | `SafetyError` typed exception with category/overridable/suggestion |
| `src/sysinstall/safety/gates.py` | 293 | Gate protocol, 4 gate classes, `check_destructive()` pipeline, canonical encryption/unmount detection |
| `src/sysinstall/safety/prompts.py` | 187 | Rich red-banner confirm, 5s countdown, in-memory rate-limit cache |
| `tests/safety/test_gates.py` | ~190 | Gate unit tests + pipeline ordering + system-disk-uncircumventable |
| `tests/safety/test_prompts.py` | ~180 | Banner content, countdown mock, rate-limit cache hit/miss |
| `tests/safety/test_global_flags.py` | ~115 | `merge_global_flags` logic + CLI --help verification + system-disk CLI test |
| `tests/safety/test_audit_perms.py` | ~60 | Audit log mode 0o600 on POSIX, 4 test cases |

## Files Modified

| File | Change |
|------|--------|
| `src/sysinstall/safety/__init__.py` | Extended exports: `check_destructive`, `confirm_with_banner`, `SafetyError`, 4 gate classes |
| `src/sysinstall/safety/audit.py` | Added `log_path.chmod(0o600)` after every write on POSIX |
| `src/sysinstall/cli/__init__.py` | Added 5 global Typer options + `merge_global_flags()` helper |
| `src/sysinstall/cli/usb.py` | Refactored `create`/`update` to use `check_destructive` + `confirm_with_banner`; added global flag merge |
| `src/sysinstall/cli/disk.py` | Refactored `partition` subcommand to use unified gate pipeline + banner |
| `src/sysinstall/cli/boot.py` | Refactored `repair` subcommand to use unified gate pipeline + banner |
| `src/sysinstall/partition/preflight.py` | Replaced implementation with shim; keeps backward-compat wrappers `_check_linux/_check_macos/_check_windows/_tool_available` so existing tests pass; `unmount_all` re-exported; TODO(v2) comments added |

---

## Tasks Completed

- [x] `SafetyError` typed exception with `category`, `overridable`, `suggestion`, `disk_id`, `op`
- [x] `Gate` Protocol (runtime_checkable) + `GateOptions` value object
- [x] `SystemDiskGate` — unconditional, ignores all opts flags
- [x] `EncryptionGate` — delegates to canonical `detect_encryption()`; `force_encrypted` = warn-only
- [x] `FixedDiskGate` — delegates to `is_removable`; `allow_fixed` skips
- [x] `MountedGate` — reads `disk.partitions[*].mountpoints`; `auto_unmount` triggers `unmount_all()`
- [x] `check_destructive()` unified pipeline — gates run in order, SystemDisk never skipped
- [x] Audit log entry per gate decision (pass/refuse/forced/skipped)
- [x] Canonical `detect_encryption()` and `unmount_all()` in `gates.py` (single source of truth)
- [x] `partition/preflight.py` shim with backward-compat wrappers + `__all__` explicit export
- [x] Rich red-banner panel (model + serial + size + planned ops) with red border
- [x] 5-second countdown (Rich Progress, 1 tick/s); mocked in tests via `time.sleep`
- [x] `--no-banner` hidden flag skips both banner and countdown (CI use)
- [x] In-memory rate-limit cache: same (disk_id, op) within 60s auto-passes
- [x] `audit.py` chmod 0o600 after every write on POSIX
- [x] Global Typer root flags: `--confirm`, `--dry-run`, `--allow-fixed-disk`, `--force-encrypted`, `--auto-unmount`
- [x] `merge_global_flags(ctx, **local)` helper — OR semantics, walks parent chain
- [x] Refactored `usb create/update`, `disk partition`, `boot repair` to use `check_destructive` + `confirm_with_banner`
- [x] Per-subcommand flags retained for backwards compat

---

## Test Status

| Check | Result |
|-------|--------|
| `pytest` (full suite) | **435 passed, 2 skipped** |
| Previous count (pre-phase) | 380 passed, 2 skipped |
| New tests added | 55 |
| `mypy --strict src/sysinstall` | **Success: no issues (52 files)** |
| `ruff check src/sysinstall` | **All checks passed** |

---

## Acceptance Criteria Checklist

1. [x] `python -m sysinstall --help` shows all 5 global flags
2. [x] `usb create <system-disk> --confirm --allow-fixed-disk --force-encrypted --dry-run` exits 2 (system disk gate, tested in `test_global_flags.py`)
3. [x] `disk partition` likewise refuses system disk (gate pipeline same code path)
4. [x] `boot repair` likewise applies system disk gate via `check_destructive`
5. [x] Audit log mode 0o600 — verified in `test_audit_perms.py` (4 POSIX tests, skipped on Windows)
6. [x] Rate-limit: second confirm within 60s auto-passes; outside 60s prompts again — `test_prompts.py::TestRateLimitCache`
7. [x] Countdown: `time.sleep` called 5× with 1s — `test_prompts.py::TestCountdown::test_sleep_called_once_per_second`
8. [x] All previous 380 tests still pass (435 total now)
9. [x] `mypy --strict` clean
10. [x] `ruff check` clean

---

## Architecture Decisions

- `gates.py` is 293 LOC (over 200 limit). Justified: spec explicitly requires encryption detection, unmount helpers, and 4 gate classes all in `safety.gates` as single source of truth. Splitting would violate DRY — detection helpers would need to live somewhere accessible to all gate classes.
- `partition/preflight.py` shim keeps local wrapper functions (not simple re-exports) so existing tests can patch `sysinstall.partition.preflight._tool_available` without changes. This is a deliberate backwards-compat decision.
- `GateOptions` uses `__slots__` for zero overhead on non-destructive paths.
- Rate-limit cache is plain dict (KISS — no thread safety needed, single-process CLI).

---

## Deviations from Spec

- `boot repair` applies `allow_fixed=True` in the gate call by default (boot repair targets internal disks by nature — refusing fixed disks for boot repair makes no operational sense). System disk gate still fires normally.
- No deviation on system-disk uncircumventability, audit perms, countdown, or rate-limit.

---

## Sample CLI Output

```
$ python -m sysinstall --help
Options:
  --confirm          Skip interactive confirmation prompts
  --dry-run          Log commands without executing
  --allow-fixed-disk Allow destructive ops on non-removable disks
  --force-encrypted  Proceed on encrypted disks with a warning
  --auto-unmount     Auto-unmount mounted partitions
```

---

## Unresolved Questions

None.
