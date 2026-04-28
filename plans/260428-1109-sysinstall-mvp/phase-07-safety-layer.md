# Phase 07 — Safety Layer

**Status**: pending
**Effort**: 1d
**Owner**: TBD
**Cross-cuts**: Phases 03, 04, 05, 06

## Context Links
- Plan: [../plan.md](./plan.md)
- Research: `research/researcher-02-disk-enumeration.md`, `-03`, `-04`, `-05`

## Overview
Centralize all destructive-operation gates: system-disk refusal, BitLocker/FileVault detection, double-confirm prompts, dry-run, structured audit logging. Earlier phases stub out checks; this phase replaces stubs with the real module and certifies each phase's gate is in place.

## Key Insights
- Safety must be one module — duplicated logic across phases drifts. DRY.
- Refusals must be **uncircumventable for system disk** — no override flag. The flag-based escapes apply only to lower-severity warnings (fixed-disk-not-removable, encrypted-source).
- Audit log = every destructive command + timestamp + user + disk-id. Helps post-incident.

## Requirements
### Functional
- `safety.check_destructive(disk, op_name)` — central gate. Raises `SafetyError` w/ category.
- `safety.confirm(prompt)` — interactive y/N + `--confirm` flag bypass.
- `safety.dry_run` — global state; when set, runners log commands instead of executing.
- Audit log: `~/.local/state/sysinstall/audit.log` (or `%LOCALAPPDATA%\sysinstall\audit.log` on Win). JSONL, one event per line.
- Rate-limit warnings: same disk, same op within 60s = no second prompt.
- Big red banner before any wipe op (TUI via Rich).

### Non-Functional
- Zero overhead in non-destructive paths.
- Audit log atomic append; never blocks main thread.

## Architecture

```
src/sysinstall/safety/
├── __init__.py              # public: check_destructive, confirm, dry_run_ctx
├── gates.py                 # SystemDiskGate, EncryptionGate, FixedDiskGate, MountedGate
├── prompts.py               # Rich confirm with red banner
└── audit.py                 # JSONL append-only log
```

```python
class SafetyError(Exception):
    category: Literal["system_disk","encrypted","fixed_disk","mounted","unknown_id"]
    overridable: bool
    suggestion: str

class Gate(Protocol):
    def check(self, disk: Disk, op: str) -> None: ...   # raises SafetyError

# Pipeline
GATES = [SystemDiskGate(), EncryptionGate(), FixedDiskGate(), MountedGate()]
def check_destructive(disk: Disk, op: str, *, allow_fixed=False, force_encrypted=False):
    for g in GATES:
        if isinstance(g, FixedDiskGate) and allow_fixed: continue
        if isinstance(g, EncryptionGate) and force_encrypted: continue
        g.check(disk, op)
    audit.record("safety_pass", disk.id, op)
```

## Gates

| Gate | Condition | Override flag | Notes |
|------|-----------|---------------|-------|
| SystemDiskGate | `disk.is_system` | NONE — never overridable | Hard refuse always |
| EncryptionGate | BitLocker/FileVault/LUKS detected | `--force-encrypted` | Warns about data + recovery key |
| FixedDiskGate | `not disk.is_removable` | `--allow-fixed-disk` | USB-create normally only on removable |
| MountedGate | any partition currently mounted | auto-unmount with `--auto-unmount` | Prompts otherwise |

## Audit Log Schema

```jsonl
{"ts":"2026-04-28T11:30:00Z","user":"alice","host":"darwin-arm64","op":"usb_create","disk_id":"usb:Kingston:5B86","cmd":["sh","Ventoy2Disk.sh","-I","-g","/dev/disk2"],"dry_run":false,"result":"ok","duration_ms":23145}
```

## Related Code Files
**Create**:
- `src/sysinstall/safety/{__init__.py,gates.py,prompts.py,audit.py}`
- `tests/safety/test_gates.py`
- `tests/safety/test_audit.py`

**Modify**:
- `src/sysinstall/ventoy/__init__.py` — call `safety.check_destructive` before runner
- `src/sysinstall/partition/__init__.py` — same
- `src/sysinstall/boot/__init__.py` — same
- `src/sysinstall/cli/__init__.py` — global `--confirm`, `--dry-run`, `--allow-fixed-disk`, `--force-encrypted` flags

## Implementation Steps

1. `gates.py` — implement 4 gates with platform-specific encryption detection:
   - macOS: `fdesetup status` parsing.
   - Linux: `lsblk -o name,fstype,type` for `crypto_LUKS`.
   - Windows: `Get-BitLockerVolume | ConvertTo-Json` (returns array).
2. `prompts.py` — Rich-based red banner with model+serial+size + planned ops summary.
3. `audit.py` — atomic append (open `O_APPEND`), JSONL line per event. Path resolution (XDG state dir on *nix, LOCALAPPDATA on Win).
4. `__init__.py` — assemble pipeline + public API.
5. Wire into phases 03/05/06 — replace any stub checks with `safety.check_destructive` call.
6. Add global Typer options to `cli/__init__.py`: `--confirm`, `--dry-run`, `--allow-fixed-disk`, `--force-encrypted`. Stored on Typer context.
7. Tests:
   - SystemDiskGate refuses always (unit).
   - EncryptionGate detects mocked BitLocker/LUKS/FileVault state (unit).
   - Audit log writes valid JSONL (unit, tmp_path).
   - Dry-run mode: confirm runners receive `dry_run=True` and don't subprocess.

## Todo
- [ ] Gate implementations + encryption detection per platform
- [ ] Rich red-banner confirm prompt
- [ ] Audit log writer
- [ ] Wire into ventoy / partition / boot
- [ ] Global CLI flags
- [ ] Tests for each gate + audit
- [ ] Sign-off check on phases 03/05/06 (gates active)

## Success Criteria
- Calling any destructive op on system disk raises `SafetyError(category="system_disk", overridable=False)` — even with all override flags set.
- BitLocker'd disk on Windows: refused unless `--force-encrypted`.
- LUKS disk on Linux: same.
- FileVault on macOS internal: refused (also caught by system-disk gate).
- `--dry-run` produces audit log entries with `dry_run: true`, no subprocess.
- Audit log line per destructive op.

## Risks
| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Encryption detection misses edge cases | Med | High | Conservative: when detection fails, treat as encrypted (refuse) — better safe |
| User shell-aliases `--confirm` always | Low | High | Show 5-second countdown banner before destructive op; can be skipped only with `--no-banner` (undocumented) |
| Audit log fills disk | Low | Low | Rotate at 100MB, keep 5 |
| Override flag confusion (typo allows wrong op) | Low | Med | Match flag exactly; no shorthand for safety overrides |

## Security Considerations
- Audit log permissions 0600 (user-only).
- No sensitive data in log (no passwords, no keys).
- All gate decisions logged — auditable.

## Test Matrix
| Test | Where |
|------|-------|
| SystemDiskGate uncircumventable | unit |
| EncryptionGate per platform | unit (mocked) |
| FixedDiskGate override path | unit |
| Audit JSONL valid | unit |
| Dry-run no subprocess | unit (mocked subprocess) |
| End-to-end refusal in CLI | integration |

## File Ownership
- `src/sysinstall/safety/*` — this phase exclusively
- Edits to ventoy/partition/boot — coordinate with their phase owners (small, mechanical)

## Rollback
Removing safety = significant regression — never roll back. If a gate is wrong, fix forward (loosen via override flag, never via removal).

## Next Steps
Phase 08 (tests) covers gate unit tests + integration. Phase 09 (docs) documents safety guarantees.
