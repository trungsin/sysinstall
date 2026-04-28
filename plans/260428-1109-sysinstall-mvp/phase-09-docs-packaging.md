# Phase 09 — Docs + Packaging

**Status**: pending
**Effort**: 2d
**Owner**: TBD
**Blocked by**: Phases 03–08 green

## Context Links
- Plan: [../plan.md](./plan.md)
- Research: `research/researcher-07-pyinstaller-packaging.md`

## Overview
Final phase. README + per-OS install guides + dual-boot walkthrough. CI matrix produces signed (where feasible) binaries on tag push. Release artifacts attached to GitHub release.

## Key Insights
- PyInstaller is per-platform, not cross-compiler — must build on each runner.
- Signing requires paid certs (~$400/yr Win + $99/yr Apple). Decision deferred to maintainer; MVP can ship unsigned with documented bypass.
- macOS requires both `codesign` + `notarytool` (altool deprecated).
- Linux: tarball + checksum file.

## Requirements
### Functional
- `README.md` with install/usage/safety sections.
- Per-OS install guides under `docs/install/{windows,macos,linux}.md`.
- Dual-boot tutorial: `docs/tutorials/dual-boot-windows-ubuntu.md` (start to finish: usb create → install Win → install Ubuntu → boot repair).
- USB tutorial: `docs/tutorials/multiboot-usb.md`.
- Troubleshooting: `docs/troubleshooting.md`.
- Architecture overview: `docs/system-architecture.md` (mermaid + module map).
- Release CI workflow produces 4 binaries on `v*` tag push.
- GitHub Releases page lists artifacts + checksums.

### Non-Functional
- README under 400 lines — link to detail docs.
- Binary <40 MB.
- Cold start <1s on target hardware.

## Architecture

```
docs/
├── project-overview-pdr.md          # what + why + non-goals
├── code-standards.md                # ruff/mypy config, naming
├── codebase-summary.md              # module map (auto-generated stub)
├── design-guidelines.md             # CLI UX conventions (red banners, confirm flags)
├── deployment-guide.md              # CI/release process for maintainers
├── system-architecture.md           # mermaid diagrams of disk/usb/boot flows
├── project-roadmap.md               # phase status, post-MVP ideas
├── project-changelog.md             # per release
├── install/
│   ├── windows.md
│   ├── macos.md
│   └── linux.md
├── tutorials/
│   ├── multiboot-usb.md
│   └── dual-boot-windows-ubuntu.md
├── troubleshooting.md
└── safety.md                        # what gates exist, what they refuse, why

.github/workflows/
├── ci.yml                           # already from phase 01 — lint+test
└── release.yml                      # new — build matrix + sign + release
```

## Release Workflow Sketch

```yaml
# .github/workflows/release.yml
name: release
on:
  push:
    tags: ["v*"]
jobs:
  build:
    strategy:
      matrix:
        include:
          - os: windows-latest
            artifact: sysinstall-windows-x64.exe
            spec: sysinstall.spec
          - os: ubuntu-22.04
            artifact: sysinstall-linux-x64
          - os: macos-13
            artifact: sysinstall-macos-x64
          - os: macos-14
            artifact: sysinstall-macos-arm64
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -e ".[dev]"
      - run: pyinstaller sysinstall.spec
      # Windows sign (if cert available)
      - if: runner.os == 'Windows' && env.SIGN_CERT_BASE64 != ''
        run: ./scripts/sign-windows.ps1
      # macOS sign + notarize
      - if: runner.os == 'macOS' && env.APPLE_ID != ''
        run: ./scripts/sign-and-notarize-macos.sh
      - run: shasum -a 256 dist/sysinstall* > dist/sha256sum.txt
      - uses: actions/upload-artifact@v4
        with: { name: ${{ matrix.artifact }}, path: dist/* }
  release:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - uses: actions/download-artifact@v4
        with: { path: artifacts }
      - uses: softprops/action-gh-release@v1
        with:
          files: |
            artifacts/**/sysinstall*
            artifacts/**/sha256sum.txt
          generate_release_notes: true
```

## Related Code Files
**Create**:
- `docs/**/*.md` per tree above
- `.github/workflows/release.yml`
- `scripts/sign-windows.ps1` (skeleton; real cert injected via secrets)
- `scripts/sign-and-notarize-macos.sh` (skeleton)

**Modify**:
- `README.md` — replace stub from phase 01
- `pyproject.toml` — add project metadata (description, urls, classifiers)

## Implementation Steps

1. Write README — TL;DR, install (3 OS), 60-second example, safety promise, link out to docs.
2. Per-OS install docs:
   - Windows: download .exe, "When SmartScreen warns: More info → Run anyway".
   - macOS: download binary, `xattr -d com.apple.quarantine` if unsigned, `chmod +x`.
   - Linux: download tarball, verify sha256, `chmod +x`, optional /usr/local/bin install.
3. Multiboot USB tutorial — full session transcript.
4. Dual-boot tutorial — order (Win first), screenshots optional, `boot repair` step.
5. Troubleshooting — common errors + fixes (Ventoy unsupported on macOS, BitLocker, chroot leak).
6. system-architecture.md — mermaid C4 diagram of modules + sequence diagrams for `usb create`, `disk partition`, `boot repair`.
7. safety.md — explicit catalogue of gates, what each refuses, escape flags.
8. release.yml workflow + signing script skeletons.
9. Test release on `v0.0.1-rc1` tag → verify all 4 artifacts produced + downloadable.
10. Add coverage + build badges to README.

## Todo
- [ ] README final
- [ ] Install docs Windows / macOS / Linux
- [ ] Tutorial: multiboot-usb
- [ ] Tutorial: dual-boot-windows-ubuntu
- [ ] Troubleshooting
- [ ] system-architecture.md with mermaid
- [ ] safety.md catalog
- [ ] release.yml CI workflow
- [ ] sign scripts (skeletons)
- [ ] Test release on rc tag
- [ ] Coverage + build badges

## Success Criteria
- Tag push `v0.0.1-rc1` produces 4 binaries on GitHub release.
- Download + run `--version` on each platform — works.
- README scannable; new user finds first command in <30s.
- Architecture doc rendered via Mermaid in GitHub.
- Safety doc lists every gate from phase 07.

## Risks
| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| macOS notarization fails on first run | High | Med | Run on rc tag first; iterate; document entitlements |
| Win SmartScreen flags unsigned binary | High (no cert) | Med | Document workaround; revisit when cert acquired |
| Binary size >40MB | Low | Low | Strip `--exclude-module` for unused stdlib chunks |
| Doc rot vs code | Med | Med | Phase 09 includes link checker in CI; doc-update task in each phase done-criteria |

## Security Considerations
- Signing secrets stored as GitHub Actions encrypted secrets.
- SHA256 published with each release.
- (Future) GPG-sign release notes once team has key.

## File Ownership
- `docs/**` — this phase
- `.github/workflows/release.yml` — this phase
- `scripts/sign-*` — this phase
- `README.md`, `pyproject.toml` metadata — this phase

## Rollback
- Bad release: `gh release delete vX.Y.Z`. Tag stays for reference.
- Doc errors: regular fix-forward via PR.

## Next Steps
Post-MVP roadmap (in `docs/project-roadmap.md`):
- Resumable downloads
- macOS USB-create via `dd` of pre-built Ventoy image
- Persistence file management (`.dat`) UI
- BIOS-mode dual-boot (legacy MBR)
- LUKS-encrypted root support in `boot repair`
- ESP backup auto-restore on `boot revert`
- Universal2 macOS binary
