---
title: GRUB Repair / Dual-Boot Finalization Research
date: 2026-04-28
type: research-report
---

# GRUB Repair After Windows Install

## Problem
Standard dual-boot install order: **Windows first, Ubuntu second**. Windows installer overwrites the EFI boot entry to point at Windows Boot Manager only, hiding GRUB. Result: PC boots straight to Windows, no menu.

(Reverse order — Ubuntu first, Windows second — same outcome: Windows clobbers EFI.)

## Fix Path A — Boot from Ubuntu live USB, run boot-repair

```bash
# In live Ubuntu session
sudo apt-add-repository ppa:yannubuntu/boot-repair
sudo apt update
sudo apt install -y boot-repair
boot-repair       # GUI; user clicks "Recommended Repair"
```

Pros: handles 95% of cases automatically. Detects Windows + Linux installs, regenerates GRUB, re-registers EFI entry.

Cons: GUI tool — sysinstall is CLI. We document it; user runs from live session.

## Fix Path B — Manual chroot + grub-install

```bash
# Boot Ubuntu live USB → terminal
sudo mount /dev/sdXn /mnt                 # Ubuntu root partition
sudo mount /dev/sdXm /mnt/boot/efi        # ESP
for d in dev proc sys run; do sudo mount --bind /$d /mnt/$d; done
sudo chroot /mnt
grub-install --target=x86_64-efi --efi-directory=/boot/efi --bootloader-id=ubuntu
update-grub
exit
```

Then verify EFI boot order:

```bash
sudo efibootmgr -v
sudo efibootmgr -o XXXX,YYYY    # Ubuntu first
```

Pros: scriptable; what sysinstall automates. Cons: requires correct partition identification — risk of pointing at wrong slice.

## sysinstall command design

```
sysinstall boot repair --ubuntu-root /dev/sdX3 --efi /dev/sdX1 [--dry-run]
```

Must run from a **Linux environment** (live USB or installed Ubuntu). On macOS/Windows host, command exits with: "Boot from Ubuntu live USB and re-run there."

Implementation:
1. Verify mounts not already in use.
2. Mount target root + ESP under `/tmp/sysinstall-chroot`.
3. Bind-mount `/dev /proc /sys /run`.
4. `chroot` and run `grub-install` + `update-grub`.
5. `efibootmgr` to verify Ubuntu entry exists, set boot order.
6. Cleanup: unmount in reverse.

## os-prober

For GRUB to *show* Windows in its menu, `os-prober` must run. Default-disabled in newer Ubuntu (security CVE-2020-14372). Enable:

```bash
echo "GRUB_DISABLE_OS_PROBER=false" | sudo tee -a /etc/default/grub
update-grub
```

sysinstall does this before the chroot exit.

## Verification

After repair, expected outputs:

```bash
efibootmgr -v
# BootCurrent: 0001
# BootOrder: 0001,0002,...
# Boot0001* ubuntu  HD(1,GPT,...)/File(\EFI\ubuntu\shimx64.efi)
# Boot0002* Windows Boot Manager  HD(1,GPT,...)/File(\EFI\Microsoft\Boot\bootmgfw.efi)
```

`/boot/grub/grub.cfg` should contain a `menuentry 'Windows Boot Manager (on /dev/sdXn)'` block.

## Edge cases

| Case | Mitigation |
|------|------------|
| Secure Boot enabled | Use `shimx64.efi` (default in Ubuntu); `--bootloader-id=ubuntu` is correct. |
| Multiple ESPs (rare, BIOS leftover + UEFI) | Pick the one with `\EFI\Microsoft\Boot\bootmgfw.efi` — that's the one Windows uses. |
| BIOS-mode (legacy MBR) install | Different code path: `grub-install /dev/sdX` with `--target=i386-pc`. sysinstall detects via `[ -d /sys/firmware/efi ]`. |
| Encrypted Linux root (LUKS) | grub-install needs `cryptodisk` module. Set `GRUB_ENABLE_CRYPTODISK=y`. v2 feature. |

## Unresolved Questions

- Should sysinstall ship its own pre-built boot-repair-cli wrapper, or just orchestrate the existing tool? (Lean toward orchestrate — DRY.)
- Windows 11 BitLocker: after GRUB repair, BitLocker may demand recovery key on next Windows boot (TPM PCR change). Document warning.
- HP/Lenovo EFI quirks where firmware ignores efibootmgr-set order. Document fallback: F12 boot menu.
