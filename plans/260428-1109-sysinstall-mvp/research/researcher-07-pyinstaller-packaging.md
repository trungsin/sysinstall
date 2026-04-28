---
title: PyInstaller Packaging + Code Signing Research
date: 2026-04-28
type: research-report
---

# PyInstaller Cross-Platform Packaging

## Verdict
**PyInstaller is not a cross-compiler.** Build per host. Use **GitHub Actions matrix** (windows-latest, ubuntu-latest, macos-latest, macos-14-arm64) to produce all four artifacts on tag push.

## Build Targets

| Target | Runner | Output | Notes |
|--------|--------|--------|-------|
| Windows x64 | windows-latest | `sysinstall.exe` | Sign with code-signing cert (Sectigo/DigiCert) — without sign, SmartScreen warns users |
| Linux x64 | ubuntu-22.04 | `sysinstall` (ELF) | No signing required; statically link minimal libs |
| macOS x64 (Intel) | macos-13 | `sysinstall` (Mach-O) | Codesign + notarize required for Gatekeeper |
| macOS arm64 (Apple Silicon) | macos-14 | `sysinstall` (Mach-O arm64) | Same — sign + notarize |

(Universal2 macOS binary is possible but doubles size — defer to v2.)

## PyInstaller invocation

```bash
pyinstaller \
  --onefile \
  --name sysinstall \
  --console \
  --hidden-import=plistlib \
  --collect-data=sysinstall \
  src/sysinstall/__main__.py
```

`--onefile` warning: macOS `.app` bundles with onefile fail Gatekeeper notarization. We're shipping a CLI binary (no `.app`), so onefile is safe — but we sign the **single binary** directly, not an app bundle.

## Code Signing

### Windows
```powershell
signtool sign /fd SHA256 /a /tr http://timestamp.digicert.com /td SHA256 sysinstall.exe
```
Requires EV (Extended Validation) cert for instant SmartScreen reputation; standard cert builds reputation over time.

### macOS (Apple Developer ID)
```bash
codesign --force --sign "Developer ID Application: <Name> (TEAMID)" \
  --options runtime \
  --entitlements entitlements.plist \
  dist/sysinstall

# Notarize
ditto -c -k --keepParent dist/sysinstall sysinstall.zip
xcrun notarytool submit sysinstall.zip --apple-id "$APPLE_ID" --team-id "$TEAM_ID" --password "$APP_PWD" --wait
xcrun stapler staple dist/sysinstall   # not needed for raw binary, but harmless
```

`entitlements.plist` for raw disk + subprocess:
```xml
<plist><dict>
  <key>com.apple.security.cs.allow-unsigned-executable-memory</key><true/>
  <key>com.apple.security.cs.allow-jit</key><true/>
</dict></plist>
```

`altool` deprecated Nov 2023 → use `notarytool`.

### Linux
No signing infra. Distribute via tarball + checksum (`sha256sums.txt`). Optionally GPG-sign the checksums file.

## Raw disk access ramifications

- Windows: signed binary still triggers UAC for Admin elevation. Code signing helps SmartScreen, doesn't bypass UAC. (We *want* UAC.)
- macOS: Hardened runtime + `--options runtime` doesn't restrict subprocess invocation of `diskutil`. We're shelling out, not calling raw IOKit, so no special entitlement.
- Linux: distro-agnostic ELF; runs anywhere with glibc 2.31+ (Ubuntu 20.04 baseline).

## CI Matrix Sketch (`.github/workflows/release.yml`)

```yaml
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
      - run: pip install -e ".[dev]" pyinstaller
      - run: pyinstaller sysinstall.spec
      # platform-specific sign step
      - uses: actions/upload-artifact@v4
        with: { name: ${{ matrix.artifact }}, path: dist/* }
  release:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - uses: actions/download-artifact@v4
      - uses: softprops/action-gh-release@v1
        with: { files: "**/sysinstall-*" }
```

## Local dev

`pip install -e .` for development — PyInstaller only used at release time. Day-to-day dev runs `python -m sysinstall ...`.

## Unresolved Questions

- Cost of EV code-signing cert (~$300/yr) — is project willing to pay? If not, ship unsigned and document SmartScreen workaround.
- Apple Developer Program ($99/yr) — same question.
- macOS minimum version: target 12 (Monterey)? Affects `subprocess` semantics minimally; mostly determined by GitHub Actions runner availability.
- Universal2 vs separate Intel/ARM macOS builds — separate is simpler, half the artifact size. Recommend separate.
