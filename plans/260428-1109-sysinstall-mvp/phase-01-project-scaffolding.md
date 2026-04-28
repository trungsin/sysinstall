# Phase 01 — Project Scaffolding

**Status**: pending
**Effort**: 1d
**Owner**: TBD

## Context Links
- Plan: [../plan.md](./plan.md)
- Research: `research/researcher-07-pyinstaller-packaging.md`

## Overview
Bootstrap Python project: src layout, Typer CLI skeleton, PyInstaller spec, dev tooling (ruff, mypy, pytest). No business logic yet — verify build pipeline works end-to-end on at least dev host.

## Key Insights
- Typer chosen over Click: type-hint based, less boilerplate, scales to deep subcommand trees (`sysinstall disk list`, `sysinstall usb create`, etc.).
- `src/sysinstall/` layout (PEP 621 / pyproject.toml) — keeps imports clean during PyInstaller bundling.
- Dev: `python -m sysinstall` (no PyInstaller). Release: PyInstaller-bundled binary.

## Requirements
### Functional
- `sysinstall --version` → prints version.
- `sysinstall --help` → top-level help.
- Subcommand groups stubbed: `disk`, `usb`, `iso`, `boot`.
- `python -m sysinstall` works in dev.

### Non-Functional
- Python 3.12+ baseline.
- Cold-start <500ms on dev hardware.
- pyproject.toml-only build (no setup.py).
- Lint clean: ruff + mypy strict on `sysinstall.cli` and `sysinstall.core`.

## Architecture

```
src/sysinstall/
├── __init__.py              # __version__
├── __main__.py              # entry: from .cli import app; app()
├── cli/
│   ├── __init__.py          # Typer app + register subcommands
│   ├── disk.py              # disk subcommand stubs
│   ├── usb.py
│   ├── iso.py
│   └── boot.py
├── core/
│   ├── __init__.py
│   ├── platform.py          # sys.platform detection helpers
│   └── logging.py           # structured logger setup
└── py.typed                 # PEP 561 marker

pyproject.toml
sysinstall.spec              # PyInstaller spec
.github/workflows/ci.yml     # lint + test (build matrix in phase 09)
README.md                    # stub
```

## Related Code Files
**Create**:
- `src/sysinstall/__init__.py`, `__main__.py`, `py.typed`
- `src/sysinstall/cli/{__init__.py,disk.py,usb.py,iso.py,boot.py}`
- `src/sysinstall/core/{__init__.py,platform.py,logging.py}`
- `pyproject.toml`
- `sysinstall.spec`
- `.github/workflows/ci.yml`
- `README.md` (stub — full docs in phase 09)
- `tests/conftest.py`, `tests/test_smoke.py`

**Modify**: none (greenfield)

## Implementation Steps

1. Create `pyproject.toml` with build-system=hatchling, deps `typer>=0.12`, `rich>=13`, `psutil>=5.9`. Dev extras: `pytest`, `pytest-cov`, `ruff`, `mypy`, `pyinstaller`.
2. `src/sysinstall/__init__.py` — set `__version__ = "0.0.1"`.
3. `cli/__init__.py` — create `app = typer.Typer()`, `app.add_typer(disk_app, name="disk")` for each subgroup, register `--version` callback.
4. Each subcommand file: empty Typer subapp + `@app.callback()` returning `Not yet implemented`.
5. `core/platform.py` — `is_windows()`, `is_macos()`, `is_linux()` helpers.
6. `core/logging.py` — Rich-based logger; respects `--verbose`/`--quiet` global options.
7. `__main__.py` — `from sysinstall.cli import app; app()`.
8. `sysinstall.spec` — onefile, console=True, hidden imports for `plistlib`.
9. `tests/test_smoke.py` — invoke `app` via `typer.testing.CliRunner`; assert `--version` exits 0.
10. `.github/workflows/ci.yml` — matrix lint+test on Win/macOS/Linux runners (build deferred to phase 09).
11. Run `pyinstaller sysinstall.spec` locally on macOS; confirm binary executes `--version`.

## Todo
- [ ] pyproject.toml with deps
- [ ] Package skeleton + Typer subgroups
- [ ] platform + logging helpers
- [ ] PyInstaller spec
- [ ] Smoke test green
- [ ] CI lint/test workflow
- [ ] Local PyInstaller build succeeds

## Success Criteria
- `python -m sysinstall --help` shows 4 subcommand groups.
- `pytest` passes (smoke test only).
- `pyinstaller sysinstall.spec` produces working binary.
- ruff + mypy clean on `cli/` and `core/`.

## Risks
| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| PyInstaller hidden-import surprises | Med | Low | Catch in this phase, add to spec |
| Typer / click version drift | Low | Low | Pin exact versions in pyproject |

## Security Considerations
- No secrets, no network in this phase.
- `.gitignore` excludes `dist/`, `build/`, `*.spec~`, `__pycache__/`.

## Rollback
Pure additive — `git revert` the scaffolding commit.

## Next Steps
Phase 02 — disk enumeration. Blocks 03, 05.
