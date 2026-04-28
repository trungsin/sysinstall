# System Architecture

## C4 Container Diagram
High-level view of system components and their interactions.

```mermaid
graph TB
    User["User"]
    CLI["sysinstall CLI<br/>(Typer)"]
    SafetyLayer["Safety Layer<br/>(Guards + Audit)"]
    Disk["Disk Module<br/>(Enumeration)"]
    Ventoy["Ventoy Module<br/>(USB Creation)"]
    Partition["Partition Module<br/>(Layout & Apply)"]
    ISO["ISO Module<br/>(Catalog & Copy)"]
    Boot["Boot Module<br/>(Repair & Detection)"]
    
    User -->|"$ sysinstall disk list"| CLI
    User -->|"$ sysinstall usb create"| CLI
    User -->|"$ sysinstall iso add"| CLI
    User -->|"$ sysinstall boot repair"| CLI
    
    CLI -->|"Validate & Log"| SafetyLayer
    CLI -->|"Call backend"| Disk
    CLI -->|"Call backend"| Ventoy
    CLI -->|"Call backend"| Partition
    CLI -->|"Call backend"| ISO
    CLI -->|"Call backend"| Boot
    
    SafetyLayer -->|"Audit trail"| AuditLog["Audit Log"]
    
    Disk -->|"Read disk info"| OSLayer["OS Layer<br/>(diskpart, lsblk,<br/>diskutil)"]
    Ventoy -->|"Download & format"| OSLayer
    Partition -->|"Create/modify partitions"| OSLayer
    ISO -->|"Copy files"| OSLayer
    Boot -->|"Read/write EFI<br/>& GRUB config"| OSLayer
```

## Module Interaction: USB Creation Sequence
Detailed sequence diagram for `sysinstall usb create --device <id> --confirm`.

```mermaid
sequenceDiagram
    User->>+CLI: usb create --device disk1 --confirm
    CLI->>CLI: Parse args, validate device ID
    CLI->>+SafetyLayer: Check gates (system disk, mounted, encrypted)
    SafetyLayer-->>-CLI: OK (gates pass)
    CLI->>+Ventoy: create_usb(device_id)
    Ventoy->>+OSLayer: Check device exists & is removable
    OSLayer-->>-Ventoy: OK
    Ventoy->>+OSLayer: Download Ventoy binary (cached)
    OSLayer-->>-Ventoy: ventoy binary
    Ventoy->>+OSLayer: Format USB (GPT, Ventoy partition)
    OSLayer-->>-Ventoy: Formatted
    Ventoy->>+OSLayer: Write bootloader to disk
    OSLayer-->>-Ventoy: Done
    Ventoy->>Ventoy: Create ventoy.json manifest
    Ventoy-->>-CLI: Success
    CLI->>SafetyLayer: Log operation
    CLI-->>-User: "USB created on disk1"
```

## Module Interaction: Disk Partitioning Sequence
Detailed sequence diagram for `sysinstall disk partition --device <id> --layout dual-boot --confirm`.

```mermaid
sequenceDiagram
    User->>+CLI: disk partition --device disk1 --layout dual-boot --confirm
    CLI->>CLI: Parse args, validate device ID
    CLI->>+SafetyLayer: Check gates (system disk, mounted, encrypted, fixed)
    SafetyLayer-->>-CLI: OK (gates pass)
    CLI->>+Partition: partition_disk(device, layout=dual-boot)
    Partition->>+Planner: design_layout(device, layout_type)
    Planner->>Planner: Calculate partition sizes<br/>(ESP 260MB, Win 400GB, Linux 500GB, Swap 8GB)
    Planner-->>-Partition: Layout plan
    Partition->>+Applier: apply_partitions(device, plan)
    Applier->>+OSLayer: Get current partition table
    OSLayer-->>-Applier: Current GPT
    Applier->>Applier: Create backup of partition table
    Applier->>+OSLayer: Delete existing partitions (if needed)
    OSLayer-->>-Applier: OK
    Applier->>+OSLayer: Create new partitions per plan
    OSLayer-->>-Applier: Partitions created
    Applier->>+OSLayer: Verify new partition table
    OSLayer-->>-Applier: Verified
    Applier-->>-Partition: Success
    Partition-->>-CLI: Success
    CLI->>SafetyLayer: Log partition changes
    CLI-->>-User: "Partitions created on disk1"
```

## Module Interaction: Boot Repair Sequence
Detailed sequence diagram for `sysinstall boot repair` (run from Ubuntu live USB).

```mermaid
sequenceDiagram
    User->>+CLI: boot repair (from Ubuntu live USB)
    CLI->>CLI: Detect live environment & target disk
    CLI->>+SafetyLayer: Check gates (encrypted, mounted)
    SafetyLayer-->>-CLI: OK
    CLI->>+BootOrch: repair_boot(target_disk)
    BootOrch->>+Backup: backup_esp(target_disk)
    Backup->>+OSLayer: Mount ESP partition (read-only)
    OSLayer-->>-Backup: ESP mounted
    Backup->>+OSLayer: Copy ESP to backup location
    OSLayer-->>-Backup: Backup created
    Backup-->>-BootOrch: Backup done
    BootOrch->>+Detector: detect_boot_setup(target_disk)
    Detector->>+OSLayer: Read EFI variables (efibootmgr)
    OSLayer-->>-Detector: Current boot entries
    Detector->>+OSLayer: Check for GRUB config on disk
    OSLayer-->>-Detector: Found or missing
    Detector-->>-BootOrch: Current setup info
    BootOrch->>+EFIModule: update_efi_entries(target_disk, boot_info)
    EFIModule->>+OSLayer: Write EFI boot entries (efibootmgr)
    OSLayer-->>-EFIModule: Boot entries updated
    EFIModule-->>-BootOrch: Done
    BootOrch->>+GRUBModule: restore_grub(target_disk)
    GRUBModule->>+Chroot: chroot_mount(target_disk)
    Chroot->>+OSLayer: Mount root partition
    OSLayer-->>-Chroot: Mounted at /mnt/target
    Chroot->>+OSLayer: Mount proc, sys, dev
    OSLayer-->>-Chroot: Virtual filesystems mounted
    Chroot-->>-GRUBModule: Chroot ready
    GRUBModule->>+OSLayer: Run grub-install via chroot
    OSLayer-->>-GRUBModule: GRUB installed
    GRUBModule-->>-BootOrch: GRUB restored
    BootOrch->>+Verify: verify_boot(target_disk)
    Verify->>+OSLayer: Check EFI boot entries
    OSLayer-->>-Verify: Entries OK
    Verify->>+OSLayer: Check GRUB config
    OSLayer-->>-Verify: Config OK
    Verify-->>-BootOrch: Verification passed
    BootOrch-->>-CLI: Success
    CLI->>SafetyLayer: Log boot repair completion
    CLI-->>-User: "Boot repair completed. You can reboot."
```

## Data Flow: Disk Enumeration
How disk information flows from OS layer to CLI output.

```mermaid
graph LR
    OS["Operating System<br/>(Windows/macOS/Linux)"]
    Native["Native Tool<br/>(diskpart, diskutil,<br/>lsblk)"]
    Enumerator["Platform-Specific<br/>Enumerator<br/>(WindowsDiskEnumerator,<br/>MacOSDiskEnumerator,<br/>LinuxDiskEnumerator)"]
    Parser["Data Parser<br/>(diskpart output,<br/>plist, lsblk JSON)"]
    Disk["Disk Model<br/>(capacity, vendor,<br/>serial, removable,<br/>encrypted)"]
    CLI["CLI Formatter<br/>(Human or JSON)"]
    User["User Output"]
    
    OS -->|"Query disk list"| Native
    Native -->|"Raw output"| Parser
    Parser -->|"Structured data"| Disk
    Enumerator -->|"Creates model"| Disk
    Disk -->|"Format for display"| CLI
    CLI -->|"Pretty-print"| User
```

## Safety Gate Evaluation Flow
How safety gates are evaluated before destructive operations.

```mermaid
graph TD
    Operation["User initiates<br/>destructive operation<br/>(partition, usb create)"]
    Gate1["System Disk Gate<br/>(Never override)"]
    Gate2["Encryption Gate<br/>(--force-encrypted)"]
    Gate3["Fixed Disk Gate<br/>(--allow-fixed-disk)"]
    Gate4["Mounted Gate<br/>(--auto-unmount)"]
    AllPass["All gates pass"]
    Refusal["Operation refused"]
    LogRefusal["Log refusal<br/>to audit trail"]
    Banner["Display red banner<br/>with changes"]
    Confirm["Require --confirm<br/>or interactive prompt"]
    Execute["Execute operation"]
    LogSuccess["Log to audit trail"]
    Done["Done"]
    
    Operation --> Gate1
    Gate1 -->|"System disk detected"| Refusal
    Gate1 -->|"Not system disk"| Gate2
    Gate2 -->|"Encrypted && no --force"| Refusal
    Gate2 -->|"OK or --force"| Gate3
    Gate3 -->|"Fixed disk && no --allow"| Refusal
    Gate3 -->|"OK or --allow"| Gate4
    Gate4 -->|"Mounted && no --auto"| Refusal
    Gate4 -->|"OK or --auto"| AllPass
    
    Refusal --> LogRefusal
    LogRefusal --> Done
    AllPass --> Banner
    Banner --> Confirm
    Confirm -->|"User confirms"| Execute
    Confirm -->|"User cancels"| Done
    Execute --> LogSuccess
    LogSuccess --> Done
```

## File Organization & Dependency Graph
Module dependencies and import structure.

```mermaid
graph TB
    CLI["CLI Layer<br/>(cli/disk.py, cli/usb.py, etc)"]
    Core["Core Utilities<br/>(core/platform.py,<br/>core/logging.py)"]
    Safety["Safety Layer<br/>(safety/guards.py,<br/>safety/audit.py)"]
    
    Disks["Disks Module<br/>(disks/base.py<br/>→ windows/macos/linux.py)"]
    Ventoy["Ventoy Module<br/>(ventoy/installer.py<br/>→ manifest.py)"]
    Partition["Partition Module<br/>(partition/planner.py<br/>→ applier.py)"]
    ISO["ISO Module<br/>(iso/catalog.py<br/>→ copy.py)"]
    Boot["Boot Module<br/>(boot/orchestrator.py<br/>→ detector/efi/grub.py)"]
    
    CLI --> Core
    CLI --> Safety
    CLI --> Disks
    CLI --> Ventoy
    CLI --> Partition
    CLI --> ISO
    CLI --> Boot
    
    Disks --> Core
    Ventoy --> Core
    Partition --> Disks
    Partition --> Core
    ISO --> Core
    Boot --> Disks
    Boot --> Core
    
    Safety --> Core
```

## Platform Abstraction Pattern
Example: How disk enumeration works across platforms.

```mermaid
graph LR
    CLI["CLI Command<br/>disk list"]
    Dispatcher["Dispatcher<br/>get_platform()"]
    Windows["Windows Path<br/>WindowsDiskEnumerator"]
    MacOS["macOS Path<br/>MacOSDiskEnumerator"]
    Linux["Linux Path<br/>LinuxDiskEnumerator"]
    
    Base["Base Interface<br/>DiskEnumerator"]
    WinImpl["WMI via<br/>PowerShell"]
    MacImpl["diskutil &<br/>plistlib"]
    LinuxImpl["lsblk JSON &<br/>sgdisk"]
    
    Output["Unified Output<br/>List[Disk]"]
    
    CLI --> Dispatcher
    Dispatcher -->|"windows"| Windows
    Dispatcher -->|"macos"| MacOS
    Dispatcher -->|"linux"| Linux
    
    Windows --> Base
    MacOS --> Base
    Linux --> Base
    
    Windows --> WinImpl
    MacOS --> MacImpl
    Linux --> LinuxImpl
    
    WinImpl --> Output
    MacImpl --> Output
    LinuxImpl --> Output
```

## Binary Build & Packaging
How source code becomes platform-specific executables.

```mermaid
graph LR
    Source["Python Source<br/>(src/sysinstall/)"]
    PyInstaller["PyInstaller<br/>sysinstall.spec"]
    WinBuild["Windows Build<br/>windows-latest"]
    MacBuild["macOS Build<br/>macos-14"]
    LinuxBuild["Linux Build<br/>ubuntu-22.04"]
    
    WinExe["sysinstall.exe<br/>~30 MB"]
    MacBin["sysinstall<br/>~30 MB<br/>arm64"]
    LinuxELF["sysinstall<br/>~25 MB<br/>ELF"]
    
    Sign["Sign Step<br/>(conditional,<br/>secrets)"]
    
    Release["GitHub Release<br/>(artifacts +<br/>checksums)"]
    
    Source --> PyInstaller
    PyInstaller --> WinBuild
    PyInstaller --> MacBuild
    PyInstaller --> LinuxBuild
    
    WinBuild --> WinExe
    MacBuild --> MacBin
    LinuxBuild --> LinuxELF
    
    WinExe --> Sign
    MacBin --> Sign
    LinuxELF --> Sign
    
    Sign --> Release
```

## Error Handling & Recovery
How errors are handled and logged.

```mermaid
graph TD
    Op["Operation<br/>(disk I/O,<br/>subprocess)"]
    Try["Try-Catch Block"]
    Success["Success"]
    Error["Exception"]
    
    Audit["Log to Audit Trail<br/>(file)"]
    UserMsg["Format User Message<br/>(short, friendly)"]
    Console["Print to Console<br/>(colored)"]
    Exit["Exit with code<br/>(0, 1, or 2)"]
    
    Op --> Try
    Try -->|"No exception"| Success
    Try -->|"Exception"| Error
    
    Success --> Audit
    Error --> Audit
    
    Audit --> UserMsg
    UserMsg --> Console
    Console --> Exit
```

## Limitations & Gaps (Documented)
- **macOS USB creation:** Ventoy upstream doesn't support macOS; documented workaround (pre-built image + `dd`)
- **Persistence files:** Ventoy `.dat` files deferred to v2 (YAGNI)
- **BIOS-mode dual-boot:** UEFI only in MVP
- **BitLocker recovery:** Warn only (no PCR sequencing)
- **Universal2 macOS binary:** arm64 only (Intel dropped per decision #3 & #10)

All limitations are documented in troubleshooting guides and relevant install docs.
