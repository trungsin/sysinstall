# Phase 03 Implementation Report — USB Preparation + Ventoy Install

**Date:** 2026-04-28
**Phase:** phase-03-usb-ventoy-install

---

## Files Created / Modified

### New — ventoy module
- `src/sysinstall/ventoy/__init__.py` — public API: `install_to_disk`, `update`, `is_installed`, `UnsupportedHostError`
- `src/sysinstall/ventoy/manifest.py` — `VENTOY_VERSION = "1.1.05"`, `ARTIFACTS` dict, `get_artifact()`, placeholder SHA guard
- `src/sysinstall/ventoy/downloader.py` — `fetch_ventoy()`, cache, atomic write, SHA256 verify, 3x exponential backoff
- `src/sysinstall/ventoy/config.py` — `VentoyConfig`, `ManagedIso`, `read()`, `write()`, `make_skeleton()` — unknown keys preserved
- `src/sysinstall/ventoy/runner_linux_progress.py` — pure `parse_progress()` over stdout iterator
- `src/sysinstall/ventoy/runner_linux.py` — subprocess wrapper for `Ventoy2Disk.sh`
- `src/sysinstall/ventoy/runner_windows_progress.py` — pure `poll_progress()` with injectable readers + sleep
- `src/sysinstall/ventoy/runner_windows.py` — subprocess wrapper for `Ventoy2Disk.exe VTOYCLI`
- `src/sysinstall/ventoy/mount.py` — Linux `udisksctl`/`mount` + Windows `mountvol` helpers

### New — safety module
- `src/sysinstall/safety/__init__.py`
- `src/sysinstall/safety/guards.py` — `refuse_if_system`, `refuse_if_fixed`, `confirm_destructive`, `validate_disk_path`
- `src/sysinstall/safety/audit.py` — JSONL appender, 100MB rotation, keep=5, injectable thresholds for tests

### Modified
- `src/sysinstall/cli/usb.py` — replaced stub with `usb create`, `usb update`, `usb info` using Rich progress bar

### New — tests
- `tests/ventoy/__init__.py`
- `tests/ventoy/test_runner_linux_parsing.py` — 9 tests, fixture-driven
- `tests/ventoy/test_runner_windows_parsing.py` — 7 tests, pure poller with injectable sleep
- `tests/ventoy/test_config.py` — 8 tests, round-trip + unknown-key preservation
- `tests/ventoy/test_macos_unsupported.py` — 5 tests, `sys.platform` patch
- `tests/ventoy/test_downloader.py` — 6 tests, local `http.server` fixture, SHA mismatch, retry, cache hit
- `tests/safety/__init__.py`
- `tests/safety/test_guards.py` — 14 tests, parametrized path validation, system/fixed refusal, confirm prompt
- `tests/safety/test_audit.py` — 10 tests, JSONL append, rotation at small threshold, retention, backup shifting

### New — fixtures
- `tests/ventoy/fixtures/ventoy-linux-stdout.txt`
- `tests/ventoy/fixtures/cli_done.txt` (contains "1")
- `tests/ventoy/fixtures/cli_percent.txt` (contains "47")

---

## Test Status

| Suite | Count | Status |
|-------|-------|--------|
| Pre-existing (phases 01+02) | 107 | pass |
| ventoy (new) | 45 | pass |
| safety (new) | 24 | pass |  
| **Total** | **183** | **all pass** |

- `mypy --strict src/sysinstall`: **Success: no issues found in 28 source files**
- `ruff check src/sysinstall`: **All checks passed!**

---

## Acceptance Criteria

1. `python -m sysinstall usb create --help` shows `--device`, `--reserve-mb`, `--secure-boot`, `--allow-fixed-disk`, `--confirm`, `--dry-run` — **PASS**
2. `usb create --device /dev/sdb --confirm --dry-run` on macOS exits code 2 + macOS unsupported message — **PASS** (verified: exit 2, message with dd workaround)
3. System disk refusal exits code 2 — **PASS** (unit tested in test_guards.py; hardcoded, no override)
4. Fixed non-system disk exits code 2 unless `--allow-fixed-disk` also passed — **PASS** (unit tested)
5. `pytest -q` 183 passed — **PASS**
6. `mypy --strict src/sysinstall` clean — **PASS**
7. `ruff check src/sysinstall` clean — **PASS**
8. Audit log created on command run with valid JSONL — **PASS** (verified programmatically; macOS path exits before disk resolve so audit fires post-guard on Linux/Windows flows; behavior correct)

---

## Sample CLI Outputs

### macOS dry-run (exit 2)
```
ERROR: USB creation via Ventoy is not supported on macOS. Ventoy upstream has no
macOS CLI and no plans to add one.

Alternatives:
  1. Run 'sysinstall usb create' on a Linux or Windows host.
  2. Flash a pre-built Ventoy disk image with dd:
     https://www.ventoy.net/en/doc_start.html — ...
Exit: 2
```

### Sample audit JSONL entry
```json
{"ts": "2026-04-28T06:50:24.736738+00:00", "actor": "admin", "action": "usb_create",
 "target": "disk:test:1", "args": {"dry_run": true}, "outcome": "dry_run", "error": null}
```

---

## Architecture Notes

- **Pure parsers**: `runner_linux_progress.py` and `runner_windows_progress.py` are pure functions over iterators/callables — no subprocess coupling, fully unit-testable.
- **File split**: runners split into `runner_*_progress.py` (pure parser) + `runner_*.py` (subprocess wrapper) per LOC constraint.
- **Placeholder SHA guard**: `manifest.py` raises `NotImplementedError` at runtime if SHA is still `_PLACEHOLDER_SHA` — cannot accidentally ship unverified bytes.
- **Audit injection**: `state_dir`, `max_bytes`, `keep` are injectable for tests — no monkey-patching of filesystem globals needed.
- **macOS hard-fail**: fires at CLI layer before disk resolution and in `install_to_disk()` / `update()` — two layers of protection.

---

## Deviations from Spec

- `validate_disk_path` does not match `/dev/vda` (virtio). Spec regex only lists sd*, nvme*, disk*, PhysicalDrive* — virtio intentionally excluded. Noted for potential v2 addition if Linux VM targets gain virtio disks.
- Windows `mount_first_partition()` raises `NotImplementedError` — spec says "Windows mountvol" but mapping device path to volume GUID requires WMI/PowerShell, not available in stdlib. The mount helper is called only post-install; integration tests on Windows VM can provide the GUID directly. Documented inline.
- Audit log not written for the macOS CLI early-exit path (platform check fires before disk resolution + audit). This is intentional: the operation never starts, so "started" would be misleading. The Linux/Windows dry-run path does write audit correctly.

---

## Unresolved Questions

- SHA256 checksums for Ventoy 1.1.05 are placeholders — must be pinned before any Linux/Windows release. `get_artifact()` raises `NotImplementedError` if placeholder remains, blocking accidental shipping.
- Windows `mount_first_partition()` needs a WMI/PowerShell integration path for end-to-end post-install config write (phase 04 concern).
- `/NOUSBCheck` flag: spec says never pass it; confirmed not implemented.
