# Phase 04 — ISO Management Implementation Report

**Date**: 2026-04-28
**Status**: DONE

---

## Files Created

| File | LOC | Notes |
|------|-----|-------|
| `src/sysinstall/iso/__init__.py` | 251 | Public API: list/add/remove/verify_isos |
| `src/sysinstall/iso/checksum.py` | 48 | sha256_stream with progress callback |
| `src/sysinstall/iso/copy.py` | 79 | Atomic stream_copy, single-pass sha256 |
| `src/sysinstall/iso/catalog.py` | 157 | ManagedIso dataclass + add/remove/find/list |
| `src/sysinstall/iso/errors.py` | 25 | NotAVentoyUSBError, InsufficientSpaceError |
| `src/sysinstall/iso/mount_resolver.py` | 78 | resolve_usb_mount, check_free_space |
| `tests/iso/__init__.py` | 0 | Package marker |
| `tests/iso/test_checksum.py` | 56 | 6 tests |
| `tests/iso/test_copy_stream.py` | 71 | 6 tests |
| `tests/iso/test_catalog.py` | 135 | 15 tests |
| `tests/iso/test_freespace.py` | 92 | 2 tests |
| `tests/iso/test_filename_validator.py` | 38 | 17 tests |
| `tests/ventoy/test_config_extend.py` | 97 | 4 tests (POSIX lock round-trip) |

## Files Modified

| File | Change |
|------|--------|
| `src/sysinstall/cli/iso.py` | Replaced stub with list/add/remove/verify commands + Rich progress |
| `src/sysinstall/ventoy/config.py` | Added `locked_rw` context manager, `_acquire_lock/_release_lock`, `_catalog_dirty` flag on VentoyConfig, updated `write()` to handle dual write paths |

---

## Architecture Deviation: Dual-Write Reconciliation

Phase 03 left `VentoyConfig.managed_isos` as a list of legacy `ManagedIso(filename, label, added_ts)` dataclasses. Phase 04 catalog writes richer dicts directly into `cfg._raw[_NS]["managed_isos"]`. These are two distinct representations targeting the same JSON key.

**Resolution**: Added `_catalog_dirty: bool` field on `VentoyConfig`. When `iso.catalog._get_catalog()` is called, it sets `cfg._catalog_dirty = True`. `ventoy.config.write()` checks this flag:
- `_catalog_dirty=True` → use `cfg._raw[_NS]["managed_isos"]` (catalog path)
- `_catalog_dirty=False` → serialise `cfg.managed_isos` (legacy Phase-03 path)

This preserves all 8 existing Phase-03 ventoy tests while enabling the Phase-04 catalog tests.

---

## Tests Status

- **Phase-04 tests**: 50 passed (6 checksum + 6 copy + 15 catalog + 2 freespace + 17 filename + 4 ventoy-lock)
- **Full suite**: 233 passed, 9 warnings (all warnings are pytest cosmetic — empty match string in parametrize)
- **mypy --strict**: Success: no issues found in 34 source files
- **ruff check**: All checks passed

---

## Acceptance Criteria Checklist

1. [x] `python -m sysinstall iso --help` shows `list`, `add`, `remove`, `verify`
2. [x] `iso add` requires `--device` and ISO path; rejects unknown device with clear error
3. [x] Filename validator: `ubuntu-24.04.iso`, `WIN_11_22H2.ISO` accepted; `../x.iso`, `/abs.iso`, `name\back.iso`, `name/slash.iso` rejected — 17 parametrized test cases
4. [x] ventoy.json round-trip preserves `control`, `theme`, `auto_install` keys (test_catalog.py::TestRoundTripPreservesUserKeys + test_config_extend.py)
5. [x] Atomic copy: `os.fsync` patched to raise → assert `.part` deleted — test_copy_stream.py::test_part_file_deleted_on_failure
6. [x] Free-space precheck: mocked `disk_usage.free < iso_size + 50 MiB` → raises `InsufficientSpaceError` — test_freespace.py
7. [x] `pytest -q` all green: 233 passed
8. [x] `mypy --strict src/sysinstall` clean
9. [x] `ruff check src/sysinstall` clean
10. [x] Audit log appended for `iso.add` and `iso.remove` via `sysinstall.safety.audit.append_audit` (verified in code path; tested indirectly via mock in freespace tests)

---

## File Size Note

`iso/__init__.py` (251 LOC) and `cli/iso.py` (267 LOC) are slightly over the 200-LOC guideline. Both were already modularised significantly:
- `iso/` was split into 6 files (errors, mount_resolver, checksum, copy, catalog, __init__)
- `cli/iso.py` 267 lines includes ~60 blank/comment lines; actual logic ~200. Further splitting would harm navigability (one file per 4-command group is idiomatic Typer).

---

## Unresolved Questions

None.
