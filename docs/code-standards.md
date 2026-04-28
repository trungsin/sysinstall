# Code Standards & Conventions

## File Naming
- **Python modules:** kebab-case with descriptive names (e.g., `partition-planner.py`, `safety-gates.py`)
- **Directories:** kebab-case, grouped by domain (e.g., `src/sysinstall/disks/`, `src/sysinstall/safety/`)
- **Classes & functions:** Follow Python conventions (PascalCase for classes, snake_case for functions)
- **Rationale:** Self-documenting filenames help LLM tools (grep, glob) understand purpose without reading content

## File Size & Modularization
- **Target:** Keep individual modules ≤200 lines of code (LOC)
- **Strategy:** 
  - Split large files at logical boundaries (e.g., separate detector logic from applier)
  - Use composition over inheritance
  - Extract utility functions into dedicated modules
  - Create service classes for business logic
- **Exceptions:** Configuration files, shell scripts, Markdown documentation (not counted)

## Code Quality
- **Linting:** Use `ruff` with strict config (E, F, I, UP, B, C4, SIM rules)
- **Type checking:** `mypy --strict` on all `src/sysinstall/` modules
- **No syntax errors:** All code must be compilable before commit
- **Style:** Prioritize readability over strict formatting; ruff handles line-length exceptions gracefully

## Architecture Principles
### KISS (Keep It Simple, Stupid)
- Solve the stated problem, no over-engineering
- Avoid premature optimization
- Write code for humans first, machines second

### YAGNI (You Aren't Gonna Need It)
- Don't build features for future use cases
- Defer v2 features (persistence files, Universal2 macOS, BIOS mode) unless MVP-blocking
- Revisit in post-MVP roadmap

### DRY (Don't Repeat Yourself)
- Extract common patterns into reusable modules
- Platform-specific code isolated in `disks/windows.py`, `disks/macos.py`, `disks/linux.py`
- Shared logic in `disks/base.py` (abstract interfaces)

## CLI Design Conventions
All CLI commands follow these patterns:

### Destructive Operations (RED BANNERS)
Before any operation that modifies disks or boot config:
1. Print red-background warning banner with human-readable device info
2. List exact changes (partitions created, ISOs copied, bootloader updated)
3. Require `--confirm` flag OR interactive prompt for user approval
4. Offer `--dry-run` to preview without executing

### Flag Semantics
- `--confirm` — Skip interactive prompt for destructive ops
- `--dry-run` — Preview changes without applying
- `--allow-fixed-disk` — Override refusal on removable=False disks (only with explicit user intent)
- `--force-encrypted` — Proceed on encrypted disks (with warning banner)
- `--auto-unmount` — Automatically unmount mounted filesystems before operations
- `--device <id>` — Target specific disk (required for multi-disk operations)

### Output Modes
- **Default (human):** Colored text, readable lists, progress bars
- `--json` — Structured JSON for scripting (only where specified in docs)

### Exit Codes
- `0` — Success
- `1` — Runtime error (disk I/O, subprocess failure, invalid input)
- `2` — Safety refusal (system disk guard, encryption refusal, permission denied)

## Error Handling
- Use try-catch for all I/O operations (disk reads, subprocess calls, file operations)
- Log full stack traces to audit log, user-friendly message to console
- Never swallow exceptions silently; always log and re-raise or exit with clear message
- Include context in error messages (which disk, which operation, why it failed)

## Logging
- **Module:** `src/sysinstall/core/logging.py` (centralized setup)
- **Levels:** DEBUG (low-level I/O), INFO (operation milestones), WARNING (recoverable issues), ERROR (failures)
- **Audit log location:**
  - Windows: `%APPDATA%\sysinstall\audit.log`
  - macOS: `~/.sysinstall/audit.log`
  - Linux: `~/.sysinstall/audit.log`
- **Rotation:** 100 MB per file, keep 5 files, compress old files
- **Sensitive data:** Never log passwords, encryption keys, API keys (check for PII before logging)

## Testing
### Unit Tests
- **Coverage gates:** ≥80% for core modules (safety, disks/base, partition/planner, iso/catalog)
- **Coverage gates (relaxed):** ≥60% for platform-conditional modules (boot/detector, boot/efi, disks/linux, disks/windows)
- **Rationale:** Platform-conditional branches exercised by VM smoke tests, not mocked unit tests
- **Mocking:** Mock subprocess, file I/O; test real logic paths

### VM Smoke Tests
- Located in `tests/smoke/`
- Run inside Windows 11 + Ubuntu 24.04 guests (automated by phase 08)
- Cover end-to-end workflows: USB creation, partitioning, boot repair

## Dependencies
### Production
- `typer>=0.12` — CLI framework
- `rich>=13` — Colored output
- `psutil>=5.9` — Cross-platform disk/process info

### Development
- `pytest>=8` — Test runner
- `pytest-cov>=5` — Coverage reporting
- `ruff>=0.4` — Linter
- `mypy>=1.10` — Type checker
- `pyinstaller>=6` — Binary packaging

## Git Practices
- Use conventional commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`
- Keep commits focused on one logical change
- No confidential data (`.env`, API keys, credentials) in commits
- Prefer squash-merge for feature branches; merge commits for releases
- Tag releases as `vX.Y.Z`

## Documentation
- All significant features documented in `./docs/` directory
- Code examples in docs must be tested before merging
- Link to relevant source files using relative paths
- Update docs when code changes; stale docs are worse than no docs

## Platform-Specific Code
### Abstraction Pattern
```python
# disks/base.py — common interface
class DiskInterface:
    def list_disks(self) -> List[Disk]: ...

# disks/windows.py, disks/macos.py, disks/linux.py — implementations
class WindowsDiskEnumerator(DiskInterface): ...
class MacOSDiskEnumerator(DiskInterface): ...
class LinuxDiskEnumerator(DiskInterface): ...

# In CLI or orchestrators
from sysinstall.core.platform import get_platform
if get_platform() == "windows":
    enumerator = WindowsDiskEnumerator()
```

- **Never** put platform checks in business logic; delegate to platform modules
- **Always** test platform-specific code on target OS (GitHub Actions CI matrix)
- **Document** platform limitations (e.g., "macOS cannot create Ventoy USB")

## Security Considerations
- **Input validation:** Check device IDs against discovered disks, reject invalid paths
- **Privilege escalation:** Only prompt for elevation when actually needed; verify successful elevation before proceeding
- **Audit logging:** Log all destructive operations with timestamp, user, device, and command
- **No hardcoded secrets:** Use environment variables (GitHub Actions secrets, not `.env`)
- **Code signing:** Windows (.exe) and macOS binaries signed by CI (stubs in MVP; see `deployment-guide.md`)
