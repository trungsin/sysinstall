# Phase 04 — ISO Management

**Status**: pending
**Effort**: 2d
**Owner**: TBD
**Blocked by**: Phase 03

## Context Links
- Plan: [../plan.md](./plan.md)
- Research: `research/researcher-01-ventoy-cli.md`

## Overview
Add/remove/list ISOs on an existing Ventoy USB. Maintains `ventoy.json` consistency, verifies ISO checksums, copies via streaming with progress.

## Key Insights
- ISO files live at root of Ventoy first partition. Ventoy auto-detects them; no registration needed for booting.
- BUT — for sysinstall-managed UX (rename, organize, persistence pairing) we maintain a `_sysinstall.managed_isos` list inside `ventoy.json` (under `_sysinstall` key — Ventoy ignores unknown root keys).
- Persistence files (`.dat`) per-ISO are opt-in (deferred from MVP unless trivial).
- macOS host CAN do ISO management (Ventoy USB's first partition is FAT32/exFAT — auto-mounts on macOS).

## Requirements
### Functional
- `sysinstall iso list --device <id>` — show ISOs on USB.
- `sysinstall iso add <iso-path> --device <id> [--checksum SHA256] [--name <alias>]`.
- `sysinstall iso remove <name-or-filename> --device <id>`.
- `sysinstall iso verify --device <id>` — re-checksum all managed ISOs.
- Refuse if device is not a Ventoy USB (no `/ventoy/ventoy.json`).
- Free-space check before copy.
- Stream copy with progress (Rich progress bar).

### Non-Functional
- Copy speed = USB hardware bound; no overhead from sysinstall layer.
- Unicode filenames preserved across Win/macOS/Linux.

## Architecture

```
src/sysinstall/iso/
├── __init__.py              # public: list_isos, add_iso, remove_iso, verify_isos
├── checksum.py              # sha256 streaming
├── copy.py                  # stream copy with progress
└── catalog.py               # _sysinstall.managed_isos in ventoy.json
```

```python
# catalog entry
@dataclass
class ManagedIso:
    filename: str           # actual file on USB (may differ from src basename)
    name: str               # user-facing alias
    sha256: str             # at-add-time hash
    size_bytes: int
    added_at: str           # ISO-8601
```

## Data Flow

```
sysinstall iso add ubuntu.iso --device usb:Kingston:5B86

  → resolve disk → mount first partition → verify ventoy.json present
  → free-space check (iso_size + 50MB headroom)
  → if --checksum given: pre-verify input ISO matches before copy
  → copy stream src → dest with progress; chunk = 4 MiB
  → compute sha256 during copy (single pass)
  → if --checksum given: assert post-copy hash == provided
  → load ventoy.json → append ManagedIso → atomic write back
  → success
```

## Related Code Files
**Create**:
- `src/sysinstall/iso/{__init__.py,checksum.py,copy.py,catalog.py}`
- `src/sysinstall/cli/iso.py` (replace stub)
- `tests/iso/test_catalog.py` — round-trip ventoy.json with sysinstall keys
- `tests/iso/test_checksum.py` — known-input sha256
- `tests/iso/test_copy_stream.py` — tempdir copy + progress callback

**Modify**:
- `src/sysinstall/cli/__init__.py` — wire iso subcommand.
- `src/sysinstall/ventoy/config.py` — extend with `managed_isos` rw.

## Implementation Steps

1. `checksum.py` — `sha256_stream(path, chunk=4*1024*1024) -> str`. Yield progress.
2. `copy.py` — `stream_copy(src, dst, *, progress_cb)`. Atomic via tempfile + rename.
3. `catalog.py` — read/write `_sysinstall.managed_isos` block. Preserve unrelated user keys.
4. `__init__.py`:
   - `list_isos(disk: Disk) -> list[ManagedIso]`
   - `add_iso(disk, src_path, name=None, expected_sha=None) -> ManagedIso`
   - `remove_iso(disk, identifier) -> ManagedIso` (also deletes file from USB)
   - `verify_isos(disk) -> list[VerifyResult]`
5. CLI commands map 1:1.
6. Validate ISO filename — strip path traversal, validate against `^[A-Za-z0-9._\- ]+\.iso$` (with unicode-letter allowance).
7. Tests: catalog round-trip preserves user-added Ventoy plugin keys.

## Todo
- [ ] checksum streaming helper
- [ ] copy with progress + atomic rename
- [ ] catalog rw with key preservation
- [ ] CLI: list, add, remove, verify
- [ ] Free-space pre-check
- [ ] Tests: catalog, checksum, copy
- [ ] Smoke on real Ventoy USB

## Success Criteria
- After `iso add ubuntu.iso`, USB boots Ventoy menu showing Ubuntu entry.
- `iso verify` re-hashes and matches stored sha256.
- `iso remove` deletes file + catalog entry; menu reflects removal.
- ventoy.json untouched keys remain unchanged after sysinstall edits (round-trip test).

## Risks
| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Concurrent edits to ventoy.json | Low | Med | File lock (fcntl/msvcrt) during read-modify-write |
| ISO too large for FAT32 (>4GB) on legacy stick | Med | Med | Detect FAT32, warn — Ventoy default is exFAT in our flow |
| Checksum mismatch mid-copy (corrupt source) | Low | Med | Stream sha256, abort on mismatch, delete partial |
| Path traversal in `--name` arg | Low | High | Sanitizer regex |
| Power loss mid-copy | Med | Low | Atomic tempfile rename — partial files left as `.part`; verify cleans up |

## Security Considerations
- sha256 verify of source if user supplies expected hash.
- Filename sanitization.
- No shell=True subprocess.
- Catalog file written atomically (tempfile + rename) to prevent corruption.

## Test Matrix
| Test | Where |
|------|-------|
| sha256 known vector | unit |
| catalog round-trip (preserves user keys) | unit |
| stream copy progress callback | unit |
| Free-space precheck | unit (mocked statvfs) |
| End-to-end add → boot | manual smoke |

## File Ownership
- `src/sysinstall/iso/*` — this phase
- `src/sysinstall/cli/iso.py` — this phase
- `src/sysinstall/ventoy/config.py` — extends; coordinate with phase 03

## Rollback
- `iso add` failure → leaves no partial file (atomic rename).
- `iso remove` records to log; user manually re-adds.
- Code: revert commit; ISOs already on USB stay.

## Next Steps
Phase 05 (HDD partitioning) is independent of this — runs in parallel.
