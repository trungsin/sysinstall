# Deployment & Release Guide

For maintainers building and releasing sysinstall binaries.

## Release Process

### 1. Prepare Release Branch
```bash
git checkout main
git pull origin main
git checkout -b release/v0.0.2
```

### 2. Update Version
Edit `src/sysinstall/__init__.py`:
```python
__version__ = "0.0.2"
```

Edit `pyproject.toml`:
```toml
version = "0.0.2"
```

### 3. Update Changelog
Edit `docs/project-changelog.md`:
```markdown
## [0.0.2] - 2026-05-15
### Added
- Dry-run support for all destructive operations
- Windows SmartScreen bypass documentation

### Fixed
- Partition planner edge case with small disks
- Boot repair chroot mount leak on Linux

### Changed
- Minimum macOS version now 12.1 (was 12.0)
```

### 4. Commit Changes
```bash
git add src/sysinstall/__init__.py pyproject.toml docs/project-changelog.md
git commit -m "chore: bump version to 0.0.2"
git push origin release/v0.0.2
```

### 5. Create Pull Request
```bash
gh pr create --title "Release v0.0.2" --body "See changelog in docs/project-changelog.md"
```

Wait for CI to pass (lint + test on Win/macOS/Linux). Merge to `main`.

### 6. Tag Release
```bash
git checkout main
git pull origin main
git tag -a v0.0.2 -m "Release v0.0.2"
git push origin v0.0.2
```

Pushing the tag triggers `.github/workflows/release.yml` automatically.

### 7. Monitor CI Build
GitHub Actions will:
1. Build on windows-latest, ubuntu-22.04, macos-14 (arm64)
2. Run signing scripts (no-op if secrets absent)
3. Upload binaries as artifacts
4. Create GitHub Release with artifacts attached

Check release page: https://github.com/trungsin/sysinstall/releases/tag/v0.0.2

## CI/CD Workflow (`.github/workflows/release.yml`)

### Build Matrix
Triggered on push to tags matching `v*` (e.g., `v0.0.1`, `v0.0.2-rc1`).

| Runner | Target | Output | Notes |
|--------|--------|--------|-------|
| `windows-latest` | Windows x64 | `sysinstall-windows-x64.exe` | Unsigned (sign script no-op) |
| `ubuntu-22.04` | Linux x64 | `sysinstall-linux-x64` | No signing |
| `macos-14` | macOS arm64 | `sysinstall-macos-arm64` | Unsigned (sign script no-op) |

**Note:** `macos-13` and `darwin/amd64` removed per locked decision #3 + #10. Apple Silicon only (M1+).

### Build Steps
For each matrix job:
1. Checkout code
2. Setup Python 3.12
3. Install dev dependencies: `pip install -e ".[dev]"`
4. Run linting (ruff + mypy) — fail fast if errors
5. Run tests with coverage — fail if <80% (strict modules)
6. Build binary: `pyinstaller sysinstall.spec`
7. Sign (Windows + macOS) — conditional, no-op if secrets absent
8. Generate SHA256 checksums
9. Upload artifacts

### Signing (Conditional)

#### Windows Signing
Script: `.github/scripts/sign-windows.ps1`

Condition: `if: env.SIGN_CERT_BASE64 != '' && env.SIGN_TIMESTAMP_URL != ''`

When triggered:
1. Decode base64 certificate from GitHub Actions secret
2. Use `signtool` to sign `.exe` with timestamp authority
3. Verify signature

**Setup (once per maintainer):**
```bash
# Acquire EV code-signing certificate from Sectigo/DigiCert (~$400/yr)
# Convert to base64:
$ base64 -i cert.pfx | tr -d '\n' > cert.base64
# Add to GitHub repo secrets:
# - SIGN_CERT_BASE64 = <base64 output>
# - SIGN_CERT_PASSWORD = <pfx password>
# - SIGN_TIMESTAMP_URL = http://timestamp.digicert.com
```

**In MVP:** Secrets absent, signing no-op. Binary ships unsigned; users see SmartScreen warning.

#### macOS Signing
Script: `.github/scripts/sign-and-notarize-macos.sh`

Condition: `if: env.APPLE_ID != '' && env.APP_PASSWORD != '' && env.TEAM_ID != ''`

When triggered:
1. Codesign binary with Developer ID Application certificate
2. Notarize with `notarytool` (Apple's service)
3. Staple notarization ticket to binary

**Setup (once per team):**
```bash
# Enroll in Apple Developer Program ($99/yr)
# Acquire Developer ID Application certificate (free, within dev program)
# Create app-specific password at https://appleid.apple.com
# Add to GitHub repo secrets:
# - APPLE_ID = <apple-id-email>
# - APP_PASSWORD = <app-specific-password>
# - TEAM_ID = <10-char team ID>
```

**In MVP:** Secrets absent, signing no-op. Binary ships unsigned; users bypass Gatekeeper warning.

#### Linux
No signing required. Ship as ELF binary; users verify via SHA256.

### Artifact Upload & Release
After all matrix jobs succeed:
1. Download all artifacts (Windows .exe, Linux ELF, macOS Mach-O)
2. Generate `sha256sum.txt`:
```
d41d8cd98f00b204e9800998ecf8427e  sysinstall-windows-x64.exe
5d41e91e98f00b204e9800998ecf8427f  sysinstall-linux-x64
...
```
3. Create GitHub Release with artifacts attached
4. Generate release notes from PR titles

## Testing Release Locally

### Build Binary Locally
```bash
# Install dev deps
pip install -e ".[dev]"

# Build binary (platform-specific)
pyinstaller sysinstall.spec

# Verify binary works
./dist/sysinstall --version
# Output: sysinstall 0.0.1

./dist/sysinstall disk list
# Output: [table of disks]
```

### Smoke Test on Each Platform
**Windows:**
```powershell
.\dist\sysinstall.exe --version
.\dist\sysinstall.exe disk list
```

**macOS:**
```bash
./dist/sysinstall --version
./dist/sysinstall disk list
# If unsigned, you may see Gatekeeper warning; right-click → Open → Allow
```

**Linux:**
```bash
./dist/sysinstall --version
./dist/sysinstall disk list
```

### RC (Release Candidate) Testing
Push tag `v0.0.2-rc1` to test release workflow before final release:
```bash
git tag v0.0.2-rc1
git push origin v0.0.2-rc1
```

CI builds artifacts; inspect GitHub release page. Download each binary and verify:
```bash
# Windows
sysinstall-windows-x64.exe --version

# macOS
chmod +x sysinstall-macos-arm64
./sysinstall-macos-arm64 --version

# Linux
chmod +x sysinstall-linux-x64
./sysinstall-linux-x64 --version
```

If all pass, push final tag `v0.0.2`.

## Binary Size & Optimization

### Target
Single binary <40 MB (no bloat from bundled Python).

### Current Status (MVP)
PyInstaller `--onefile` produces arm64 binary ~30 MB. Monitor in each release.

### Optimization (if needed)
1. **Exclude unused stdlib:** Modify `sysinstall.spec` with `excludes=["tkinter", "unittest.mock", ...]`
2. **Strip debug symbols:** Use `pyinstaller --strip` (added to spec)
3. **UPX compression:** Enable `upx=True` in spec (reduces startup time on slower disks)

## Backward Compatibility

### API Stability
- CLI flags are public API; renaming breaks scripts
- Exit codes are public API; changing meaning breaks CI pipelines
- JSON schema is public API; adding required fields breaks parsers

Before removing/renaming flags:
1. Announce deprecation in release notes (v0.1)
2. Print warning when deprecated flag used (v0.1+)
3. Remove in v0.2+ (not before 2 minor releases)

### Code Signing Transition
**MVP (v0.0.1):** Unsigned binaries, documented bypass

**v0.1.0 (mid-year):** Acquire certs if budget allows; sign and notarize

**v1.0.0:** Require signing (no more unsigned releases)

## Hotfix Release
For critical bugs (e.g., data loss, security):

```bash
git checkout main
git pull
git checkout -b hotfix/v0.0.1-patch1
# Fix bug, update version, update changelog
git commit -m "fix: critical bug XYZ"
git push origin hotfix/v0.0.1-patch1
gh pr create --title "Hotfix v0.0.1-patch1"
# Merge after CI passes
git tag v0.0.1-patch1
git push origin v0.0.1-patch1
```

## Documentation Before v0.1.0 Release
**TODO BEFORE v0.1.0:** Confirm Ventoy SHA256 hashes in `src/sysinstall/ventoy/manifest.py`.

Current value (placeholder):
```python
VENTOY_VERSION = "1.1.05"
VENTOY_SHA256_WINDOWS = "placeholder_hash_windows"
VENTOY_SHA256_LINUX = "placeholder_hash_linux"
```

Before v0.1.0:
1. Download Ventoy 1.1.05 from official repo
2. Verify signatures
3. Extract and compute SHA256 hashes
4. Update constants in code
5. Add hash verification to CI
6. Commit with message: `chore: pin Ventoy 1.1.05 hashes`

## Security Checklist
- [ ] No credentials (API keys, certs) hardcoded in source
- [ ] All secrets added to GitHub Actions secrets (not `.env`)
- [ ] Release notes don't leak internal details
- [ ] Binary size <40 MB (no surprise bloat)
- [ ] Tests pass on all platforms (Windows, macOS arm64, Linux)
- [ ] Changelog updated
- [ ] Git tag matches version string

## Rollback
If release is broken:

```bash
# Delete release
gh release delete v0.0.2

# Keep tag for reference (do NOT delete)
# Tag remains in git history; maintainers can see what was shipped

# Fix code on main, bump version, re-release
# e.g., v0.0.3
```

## FAQ

**Q: How do I test signing locally?**
A: Signing scripts are platform-specific and require certificates. In MVP, test workflow by running `sign-windows.ps1` / `sign-and-notarize-macos.sh` locally with mocked outputs; CI tests real flow.

**Q: Can I release from a branch other than main?**
A: No. Always merge to main first, then tag main. This keeps release history linear.

**Q: What if a test fails on the macOS runner?**
A: CI blocks release. Fix test, push fix, re-run. If test is platform-specific (only fails on M1), escalate to team; may be infrastructure issue.

**Q: Do I need to sign binaries for MVP?**
A: No. Documented bypass is acceptable for v0.0.x. Plan to acquire certs before v0.1.0 if project is active.
