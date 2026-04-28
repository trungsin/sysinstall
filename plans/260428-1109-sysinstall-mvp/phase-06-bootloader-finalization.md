# Phase 06 — Bootloader / Dual-Boot Finalization

**Status**: pending
**Effort**: 2d
**Owner**: TBD
**Blocked by**: Phase 05

## Context Links
- Plan: [../plan.md](./plan.md)
- Research: `research/researcher-06-grub-repair.md`

## Overview
Restore GRUB after Windows install. Runs from Ubuntu live USB session ONLY (Linux env required for `grub-install`, `efibootmgr`, chroot). Detects ESP + Ubuntu root partition, performs chroot-based reinstall, registers EFI entry.

## Key Insights
- GRUB repair requires Linux env. macOS / Windows host: command exits with "boot from live USB" instruction.
- The fix is mechanical and well-documented (`grub-install` + `update-grub` in chroot). Risk = wrong partition selected.
- `os-prober` must be re-enabled (default off in newer Ubuntu) for GRUB menu to show Windows.
- BIOS-mode (MBR) install needs different `--target=i386-pc` invocation. Detect via `/sys/firmware/efi`.

## Requirements
### Functional
- `sysinstall boot detect` — analyze current system, list candidate ESP + Linux roots, identify firmware mode.
- `sysinstall boot repair --ubuntu-root <part-id> --efi <part-id> [--no-os-prober] [--dry-run] [--confirm]`.
- Auto-mount ESP + root + bind-mounts under `/tmp/sysinstall-chroot-<rand>`.
- Run `grub-install` (efi or bios target) + `update-grub` inside chroot.
- Verify `efibootmgr` shows Ubuntu entry post-run; set boot order Ubuntu first.
- Cleanup: unmount in reverse order on success AND on failure.

### Non-Functional
- Idempotent: safe to run twice.
- Restore from failure: never leave bind-mounts dangling.

## Architecture

```
src/sysinstall/boot/
├── __init__.py              # public: detect(), repair()
├── detector.py              # firmware mode + candidate partitions
├── chroot.py                # mount/unmount/bind-mount manager (context manager)
├── grub.py                  # grub-install + update-grub commands
└── efi.py                   # efibootmgr wrapper
```

```python
@dataclass(frozen=True)
class BootEnvironment:
    firmware: Literal["uefi","bios"]
    candidate_efi: list[Partition]
    candidate_linux_roots: list[Partition]
    candidate_windows: list[Partition]

@dataclass(frozen=True)
class RepairPlan:
    firmware: Literal["uefi","bios"]
    efi_partition: Partition
    root_partition: Partition
    enable_os_prober: bool
    set_boot_order_first: bool
```

## Data Flow

```
sysinstall boot repair --ubuntu-root <id> --efi <id> --confirm

  → host check: must be Linux (else exit with "boot live USB" message)
  → detector: confirm partitions exist + look correct (root has /etc/os-release, EFI has /EFI/)
  → build RepairPlan
  → confirm prompt (ALWAYS — even with --confirm shows partitions)
  → ChrootContext:
      mount root → /tmp/sysinstall-chroot
      mount efi  → /tmp/sysinstall-chroot/boot/efi
      bind-mount /dev /proc /sys /run
      yield
  → inside chroot:
      if uefi:
        grub-install --target=x86_64-efi --efi-directory=/boot/efi --bootloader-id=ubuntu
      else:
        grub-install --target=i386-pc /dev/<parent-disk>
      if enable_os_prober:
        sed -i 's/.*GRUB_DISABLE_OS_PROBER.*/GRUB_DISABLE_OS_PROBER=false/' /etc/default/grub
        # or append if not present
      update-grub
  → outside chroot (still root):
      efibootmgr -v → assert "ubuntu" entry exists
      if set_boot_order_first: efibootmgr -o <ubuntu-num>,<rest>
  → cleanup (always; finally clause)
  → final report: BootOrder, menu entries
```

## Related Code Files
**Create**:
- `src/sysinstall/boot/{__init__.py,detector.py,chroot.py,grub.py,efi.py}`
- `src/sysinstall/cli/boot.py` (replace stub)
- `tests/boot/test_detector.py`
- `tests/boot/test_chroot_seq.py` — mount/unmount call sequence with mocked subprocess
- `tests/boot/test_efi_parser.py` — efibootmgr -v output parsing

**Modify**:
- `src/sysinstall/cli/__init__.py` — wire boot subcommand.

## Implementation Steps

1. `detector.py`:
   - `is_uefi() -> bool` — check `/sys/firmware/efi`.
   - `find_candidates() -> BootEnvironment` — walk partitions; ESP candidates have `fs=fat32` + `parttype=ef00`; root candidates mount + have `/etc/os-release`; Windows candidates have NTFS + `/Windows/System32/`.
2. `chroot.py` — context manager. Tracks active mounts in a list; finally-block unmounts in reverse. Use `mount --bind` for `/dev /proc /sys /run`.
3. `grub.py` — `install_uefi(chroot_root)` + `install_bios(chroot_root, disk)`. `update_grub(chroot_root)`. `enable_os_prober(chroot_root)`.
4. `efi.py` — parse `efibootmgr -v` output → list of EfiEntry(num, label, path). `set_boot_order(entries)`.
5. `__init__.py` — `repair(plan: RepairPlan)`. Pre-check Linux host. Run flow above.
6. CLI:
   - `boot detect` — pretty-print BootEnvironment.
   - `boot repair` — accept partition IDs, build plan, execute.
7. Tests:
   - Detector: feed fake `lsblk` JSON + faked `/etc/os-release` content via tmp_path.
   - Chroot manager: assert exact mount/umount sequence with mocked subprocess.
   - efi parser: real-world `efibootmgr -v` fixture text.

## Todo
- [ ] detector.py: firmware mode + candidate partitions
- [ ] chroot.py context manager with reverse-cleanup
- [ ] grub.py wrappers
- [ ] efi.py with efibootmgr parser
- [ ] CLI `boot detect` + `boot repair`
- [ ] Linux-host gate (else helpful exit)
- [ ] Tests: detector, chroot seq, efi parser
- [ ] Manual smoke on dual-boot VM

## Success Criteria
- `boot detect` correctly identifies ESP + Ubuntu + Windows on a triple-partition test VM.
- After deliberately clobbering EFI entry on test VM, `boot repair` restores GRUB; reboot shows GRUB menu with both Ubuntu + Windows.
- On macOS / Windows host: clear "boot Ubuntu live USB and re-run" message, exit 2.
- Cleanup verified: `mount` shows no `/tmp/sysinstall-chroot*` after run (success or fail).

## Risks
| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Wrong root partition specified | Med | High | Detector verifies `/etc/os-release` before chroot |
| Wrong ESP specified (multiple ESPs) | Med | High | Pick ESP containing `\EFI\Microsoft\Boot\bootmgfw.efi` (Windows ref) when ambiguous |
| Bind-mount leak on crash | Med | Med | `try/finally` cleanup; idempotent unmount; `lsof` advisory if busy |
| BitLocker recovery key prompt on next Win boot | Med | Med | Document warning in pre-confirm message |
| Secure Boot misconfigured | Low | Med | Default to shimx64.efi (Ubuntu's signed shim) |
| BIOS-mode disk needs MBR not GPT | Low | High | Detector flags + uses `i386-pc` target |

## Security Considerations
- Operations require root — auto re-exec via `sudo` instruction (no implicit elevation).
- All command paths validated (no shell=True).
- chroot mountpoint randomized to avoid collision with concurrent runs.
- After run, dump full audit log of commands to `~/.local/state/sysinstall/boot-repair-<ts>.log`.

## Test Matrix
| Test | Where |
|------|-------|
| Detector with mocked /sys/firmware + lsblk fixture | unit |
| Chroot mount/unmount sequence (mocked subprocess) | unit |
| efibootmgr parser | unit (fixtures) |
| End-to-end repair | VM with deliberate EFI clobber |

## File Ownership
- `src/sysinstall/boot/*` — this phase
- `src/sysinstall/cli/boot.py` — this phase

## Rollback
- Pre-repair: snapshot ESP contents to `~/.local/state/sysinstall/esp-backup-<ts>.tar`. On user request `boot revert`, untar back.
- Code: revert commit; ESP backup remains for manual restore.

## Next Steps
Phase 07 (safety) hardens this phase's pre-flight gates before declaring done.
