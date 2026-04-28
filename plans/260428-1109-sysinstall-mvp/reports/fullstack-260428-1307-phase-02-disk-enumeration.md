# Phase 02 Implementation Report — Disk Enumeration

**Date:** 2026-04-28  
**Phase:** 02 — Cross-Platform Disk Enumeration  
**Status:** DONE

---

## Files Created

| File | Lines | Notes |
|------|-------|-------|
| `src/sysinstall/disks/__init__.py` | 52 | Public API + backend selector |
| `src/sysinstall/disks/base.py` | 47 | `Partition`, `Disk` frozen dataclasses, `DiskBackend` Protocol, `BackendUnavailable` |
| `src/sysinstall/disks/identifiers.py` | 49 | `make_stable_id` + `_short_hash` (blake2b 8-byte hex) |
| `src/sysinstall/disks/macos.py` | 263 | diskutil backend + APFS container filter |
| `src/sysinstall/disks/linux.py` | 182 | lsblk JSON backend |
| `src/sysinstall/disks/windows.py` | 220 | PowerShell Get-Disk/Get-Partition/Get-Volume backend |
| `tests/disks/__init__.py` | 0 | Package marker |
| `tests/disks/test_macos_parser.py` | 183 | 28 tests |
| `tests/disks/test_linux_parser.py` | 130 | 29 tests |
| `tests/disks/test_windows_parser.py` | 115 | 25 tests |
| `tests/disks/test_identifiers.py` | 97 | 22 tests |
| `tests/disks/fixtures/diskutil-plist.xml` | 96 | Sanitised (no real serials) |
| `tests/disks/fixtures/lsblk.json` | 64 | 2 disks: SATA system + USB removable |
| `tests/disks/fixtures/powershell-disk.json` | 80 | 2 disks: NVMe system + USB |

## Files Modified

| File | Change |
|------|--------|
| `src/sysinstall/cli/disk.py` | Replaced stub with full `list` and `show` commands |

---

## Tasks Completed

- [x] base.py dataclasses + Protocol
- [x] identifiers.py stable-id helper
- [x] macOS backend + parser tests
- [x] Linux backend + parser tests
- [x] Windows backend + parser tests
- [x] CLI `disk list` + `disk show` (with `--json`)
- [x] Backend selector
- [x] Host-conditional integration (live run on dev macOS)

---

## Tests Status

- **Type check (mypy --strict):** PASS — 14 files, no issues
- **Linting (ruff check):** PASS — all checks passed
- **Unit tests:** 107 passed (104 disk tests + 3 smoke), 0 failed, 0 skipped

Test breakdown:
- `test_identifiers.py`: 22 tests (determinism, unstable prefix, safe chars, all bus types)
- `test_macos_parser.py`: 28 tests (list parsing, bus mapping, system detection, build_disk_from_info)
- `test_linux_parser.py`: 29 tests (fixture-based, edge cases, no-serial fallback)
- `test_windows_parser.py`: 25 tests (fixture-based, single-object JSON, empty input)
- `test_smoke.py`: 3 tests (version, help)

---

## Acceptance Criteria

| # | Criterion | Status |
|---|-----------|--------|
| 1 | `disk list` on dev macOS returns ≥1 disk, internal SSD `is_system=True` | PASS |
| 2 | `disk list --json` outputs valid JSON | PASS |
| 3 | `disk show <id>` works for enumerated ID | PASS |
| 4 | `pytest -q` all green | PASS — 107 passed |
| 5 | `mypy --strict` clean | PASS |
| 6 | `ruff check` clean | PASS |
| 7 | Stable IDs identical across two consecutive runs | PASS |
| 8 | No-serial disk uses `unstable:` prefix | PASS |

---

## Sample Output

```
                             Physical Disks
+---------------------------+--------+--------+----------------+------+---------+--------+
| ID                        | Path   | Size   | Model          | Bus  | Remov.  | System |
+---------------------------+--------+--------+----------------+------+---------+--------+
| unstable:a591dd2b8f7d157a | /dev/… | 465.9  | APPLE SSD      | nvme | no      | YES    |
|                           |        | GB     | AP0512Q        |      |         |        |
+---------------------------+--------+--------+----------------+------+---------+--------+
```

Note: IDs are `unstable:` because Apple Silicon NVMe controller does not expose
serial numbers via `diskutil info` (no `IOSerialNumber` key). The `unstable:`
prefix correctly signals this. All other acceptance criteria pass.

---

## Deviations from Spec

1. **APFS container filtering in `parse_diskutil_list`**: The spec says iterate `WholeDisks`, but on a real Apple Silicon machine `WholeDisks` includes synthesized APFS container disks (disk1/disk2/disk3). Decision #6 ("whole disks only, skip APFS synthesised volumes") was applied by checking `APFSPhysicalStores` presence in `AllDisksAndPartitions` to exclude these. This matches the locked decision intent.

2. **APFS volume → physical disk association**: The backend resolves APFS volumes from container entries back to the physical disk by tracing `APFSPhysicalStores` → partition → whole disk. This is the only way to correctly set `is_system=True` on the physical NVMe on Apple Silicon.

3. **macOS serial**: Apple Silicon NVMe does not report `IOSerialNumber` in `diskutil info -plist`. IDs are correctly `unstable:` per spec requirement #8.

---

## Unresolved Questions

None — all spec requirements implemented and passing.
