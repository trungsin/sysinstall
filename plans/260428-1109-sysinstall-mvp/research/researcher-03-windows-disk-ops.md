---
title: Windows Disk Operations + Elevation Research
date: 2026-04-28
type: research-report
---

# Windows Disk Operations

## Strategy
Shell out to **PowerShell Storage cmdlets** (preferred). Fall back to `diskpart` script files for legacy. Avoid WMIC (deprecated 24H2+).

## PowerShell Storage Cmdlets

```powershell
# Enumerate
Get-Disk | ConvertTo-Json -Depth 5
Get-Partition -DiskNumber N | ConvertTo-Json
Get-Volume | ConvertTo-Json

# Wipe + repartition (requires Admin)
Clear-Disk -Number N -RemoveData -RemoveOEM -Confirm:$false
Initialize-Disk -Number N -PartitionStyle GPT
New-Partition -DiskNumber N -Size 512MB -DriveLetter S | Format-Volume -FileSystem FAT32 -NewFileSystemLabel "EFI"
New-Partition -DiskNumber N -UseMaximumSize -DriveLetter W | Format-Volume -FileSystem NTFS -NewFileSystemLabel "Windows"
```

For dual-boot layout we want:
1. EFI System Partition (ESP) — 512 MB FAT32
2. Microsoft Reserved Partition (MSR) — 16 MB
3. Windows partition — NTFS (size from user)
4. Linux root — ext4 (created later from Ubuntu installer or sysinstall using WSL/parted)
5. Linux swap (optional) — user choice

PowerShell can create #1–3 directly. ext4 cannot be created natively on Windows — sysinstall reserves the space as **unallocated** and lets the Ubuntu installer format it, OR uses a Linux live USB.

## Admin Elevation (UAC)

```python
import ctypes, sys
def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() == 1
    except Exception:
        return False

def relaunch_as_admin():
    rc = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, " ".join(sys.argv), None, 1
    )
    if rc <= 32:
        raise PermissionError(f"UAC elevation failed (rc={rc})")
    sys.exit(0)
```

**ShellExecuteW return codes**: >32 success, ≤32 failure (5=access denied/user cancelled UAC).

**Strategy**: at command entry, check `is_admin()`. If not and command needs Admin (`usb create`, `disk partition`, `boot repair`), prompt user with explicit message ("This command needs Administrator. Click Yes on the UAC dialog.") then `relaunch_as_admin()`.

**Caveat**: When elevated, working directory resets to `C:\Windows\System32`. Pass absolute paths only. Mapped drives disappear in elevated session — use UNC paths.

## Subprocess pattern

```python
def run_pwsh(script: str, *, capture=True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive",
         "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=capture, text=True, check=False
    )
```

Always pass `-NoProfile -NonInteractive` for determinism. Parse JSON output via `json.loads(proc.stdout)`.

## diskpart fallback

For systems where PowerShell Storage module is missing (rare, Server Core minimal):

```
# script.txt
select disk 1
clean
convert gpt
create partition efi size=512
format quick fs=fat32 label="EFI"
...
exit
```

Invoke: `diskpart /s script.txt`. Less robust (no JSON output), use only as fallback.

## Disk identification stability

PowerShell `Get-Disk.Number` is **NOT stable across reboots**. Use `UniqueId` (combination of bus + serial) for persistent ID. sysinstall stores `UniqueId` in plan files, resolves to current `Number` at runtime.

## Unresolved Questions

- Does `Clear-Disk` on a USB containing existing Ventoy installation succeed? (Tentative: yes, with `-RemoveData`.)
- ARM64 Windows — does Storage module behave identically? Need test on Surface Pro X-class.
- BitLocker-encrypted source disk: how to detect + warn before partition? `Get-BitLockerVolume` available only when feature installed.
