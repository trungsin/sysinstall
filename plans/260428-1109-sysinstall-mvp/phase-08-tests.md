# Phase 08 — Tests

**Status**: pending
**Effort**: 3d
**Owner**: TBD
**Gates merge of**: 03, 04, 05, 06

## Context Links
- Plan: [../plan.md](./plan.md)

## Overview
Two layers: (1) **unit tests** with mocked subprocess + fixture stdout — fast, deterministic, run on every PR. (2) **VM smoke tests** — slow, manual or scheduled, validate end-to-end on real OS.

## Key Insights
- Disk operations CANNOT be unit-tested for real on CI — too dangerous. Mock subprocess, assert command shape.
- Fixture-based parser tests cover schema variability across platform tool versions.
- Smoke tests run in QEMU/UTM with disposable disk images. Each phase has 1–2 smoke scenarios.
- Coverage target: 80% on `safety/`, `disks/`, `partition/planner.py`, `iso/catalog.py`. Lower acceptable on platform-specific runner code (covered by VM smoke).

## Requirements
### Functional
- Unit tests run via `pytest` <30s on dev machine.
- VM smoke runs via `make smoke-linux` / `make smoke-windows` against pre-built QEMU images.
- CI matrix: ubuntu-latest, windows-latest, macos-latest run unit tests on every push.
- Coverage report uploaded as artifact.

### Non-Functional
- No real disk writes from CI ever.
- VM smoke tests are reproducible — pinned ISO + image versions.

## Test Layers

### Unit (PR gate)
| Module | Test focus |
|--------|------------|
| `disks/macos.py` | parse fixture plist → Disk dataclass |
| `disks/linux.py` | parse fixture lsblk JSON |
| `disks/windows.py` | parse fixture PowerShell JSON |
| `ventoy/downloader.py` | sha256 verification + retry |
| `ventoy/runner_*` | command shape + progress parsing |
| `ventoy/config.py` | round-trip preserves user keys |
| `iso/catalog.py` | atomic ventoy.json edits |
| `iso/checksum.py` | known-vector sha256 |
| `partition/planner.py` | layout fits / rejects too-small |
| `partition/runner_*` | exact command-list generation |
| `boot/detector.py` | candidate identification |
| `boot/chroot.py` | mount/unmount sequence (mocked subprocess) |
| `boot/efi.py` | efibootmgr -v parser |
| `safety/gates.py` | each gate refuses correctly |
| `safety/audit.py` | JSONL append valid |
| CLI smoke | `--help`, `--version`, dry-runs |

### Integration (host-conditional, in CI)
| Test | Host | Notes |
|------|------|-------|
| `disk list` returns ≥1 disk | all 3 OS | host runner's own disk |
| `boot detect` on Linux runner | Linux | non-destructive read |

### VM Smoke (manual/nightly)
| Scenario | VM | Pass criteria |
|----------|----|---------------| 
| usb create on Linux | Ubuntu 24.04 + USB passthrough | bootable Ventoy USB |
| usb create on Windows | Win11 + USB passthrough | bootable Ventoy USB |
| iso add → boot | post-create USB | Ubuntu boots from menu |
| disk partition dual-boot | Ubuntu, blank target disk | GPT layout matches plan |
| boot repair after EFI clobber | dual-boot Ubuntu+Win11 | GRUB menu restored |
| safety: refuse system disk | all 3 OS | hard refusal observed |

## Architecture

```
tests/
├── conftest.py              # tmp_path, mocked subprocess, host-skip helpers
├── fixtures/
│   ├── disks/
│   │   ├── diskutil-macos-internal-ssd.plist
│   │   ├── diskutil-macos-usb-stick.plist
│   │   ├── lsblk-ubuntu-with-usb.json
│   │   └── powershell-disk-list.json
│   ├── ventoy/
│   │   ├── ventoy.json.user-edited
│   │   ├── cli_done-success.txt
│   │   └── ventoy-linux-stdout.txt
│   ├── boot/
│   │   ├── efibootmgr-typical.txt
│   │   └── lsblk-dual-boot.json
│   └── partition/
│       └── plan-default-500gb.json
├── disks/test_*.py
├── ventoy/test_*.py
├── iso/test_*.py
├── partition/test_*.py
├── boot/test_*.py
├── safety/test_*.py
├── cli/test_smoke.py
└── smoke/                   # not run by default; manual or nightly
    ├── README.md
    ├── linux_usb_create.sh
    ├── windows_usb_create.ps1
    └── boot_repair_dualboot.sh
```

## Mocking Strategy

```python
# conftest.py
@pytest.fixture
def mock_subprocess(monkeypatch):
    calls = []
    def fake_run(cmd, *args, **kwargs):
        calls.append({"cmd": cmd, "kwargs": kwargs})
        return SimpleNamespace(returncode=0, stdout=fixtures_for(cmd), stderr="")
    monkeypatch.setattr(subprocess, "run", fake_run)
    return calls
```

Tests assert `calls` contains expected commands in order, never executes anything real.

## Related Code Files
**Create**: `tests/**` per tree above.
**Modify**: `pyproject.toml` (test deps already there from phase 01).

## Implementation Steps

1. Set up `conftest.py` with `mock_subprocess`, `host_skip` fixtures.
2. Capture real-host output samples → fixtures (run `diskutil list -plist > tests/fixtures/disks/diskutil-macos-internal-ssd.plist` on dev machine, sanitize serials).
3. Write parser tests per backend (data-driven via `pytest.mark.parametrize`).
4. Write runner cmd-gen tests — assert exact subprocess args.
5. Write safety gate tests — mock encryption-detection helpers, assert refusal.
6. Write CLI smoke tests via `typer.testing.CliRunner`.
7. Set up VM smoke harness — Makefile targets, README with manual steps.
8. Configure GitHub Actions to run `pytest --cov` on matrix.
9. Add coverage badge to README.

## Todo
- [ ] conftest fixtures + helpers
- [ ] Disk parser fixtures captured + sanitized
- [ ] Disk parser tests (3 backends)
- [ ] Ventoy runner + downloader tests
- [ ] ISO catalog + checksum tests
- [ ] Partition planner + runner cmd-gen tests
- [ ] Boot detector + chroot + efi tests
- [ ] Safety gate + audit tests
- [ ] CLI smoke tests
- [ ] VM smoke scripts (Linux + Windows)
- [ ] Coverage report uploaded in CI
- [ ] All unit tests pass on Win/macOS/Linux runners

## Success Criteria
- `pytest` green on all 3 CI runners.
- Coverage ≥80% on `safety/`, `disks/`, `partition/planner.py`, `iso/catalog.py`, `boot/detector.py`, `boot/efi.py`.
- VM smoke scripts execute end-to-end (manual, documented).
- No CI test ever calls real disk-write subprocess (verified by `mock_subprocess` always-fixture).

## Risks
| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Fixture rot (tool output schema changes) | Med | Med | Re-capture on minor releases; tolerant parsers |
| Mocked tests pass but real binary fails | Med | High | VM smoke tests catch this — gate releases |
| Slow tests on Win runner | Med | Low | Parallelize with pytest-xdist |
| Sensitive data in captured fixtures (serials) | Med | Low | Sanitizer script normalizes serials → "TESTSERIAL000" |

## Security Considerations
- Fixtures sanitized — no real serials, MAC addresses, machine IDs.
- Smoke test images downloaded from official sources, sha256 pinned.

## File Ownership
- `tests/**` — this phase
- Coordinates with all phase owners for fixture capture

## Rollback
Tests are additive — never roll back tests. Failing test = fix product, not delete test.

## Next Steps
Phase 09 (docs + packaging) — depends on tests green.
