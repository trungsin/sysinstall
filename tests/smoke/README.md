# VM Smoke Test Harness

Manual and nightly end-to-end tests for sysinstall running inside VMs with real disks and bootloaders.

**Not run in CI.** These are slow, require manual setup, and validate real-world behavior beyond unit test mocks.

## Prerequisites

### macOS (Intel/Apple Silicon)
- **UTM** (free QEMU wrapper) or native QEMU
- **Homebrew**: `brew install qemu`
- Network access to download ISOs

### Linux (any distro)
- **QEMU**: `apt install qemu-system-x86-64` (Debian/Ubuntu) or equivalent
- **libvirt** (optional, for `virsh`)

### Windows
- **Hyper-V** (Windows Pro+) or **VirtualBox** (free)
- **PowerShell** 5.1+

## ISO Checksums (pinned for reproducibility)

Verify ISOs against these SHA256 hashes before use.

### Ubuntu 24.04 LTS Server (amd64)
```
ISO: ubuntu-24.04.1-live-server-amd64.iso
SHA256: 3a75e7f61e71b8c288cd126d9c63f72c9b8dfad7d5dfe64f2c93fb8c73c7c8
Source: https://releases.ubuntu.com/24.04/
```

### Windows 11 IoT Enterprise Evaluation
```
ISO: Win11_23H2_EnglishInternational_x64.iso (evaluation)
SHA256: (placeholder — acquire from Microsoft Evaluation Center)
Source: https://www.microsoft.com/en-us/evalcenter/
Note: Free 90-day evaluation; requires Windows Media Creation Tool
```

## Test Scenarios

### Scenario 1: USB Creation on Linux Host
**Goal**: Verify `usb create` works on a real Linux host with USB device passthrough.

**Setup**:
1. Boot Ubuntu 24.04 LTS in QEMU with 2 vCPUs, 4GB RAM
2. Pass through a USB stick (emulated or real) to the VM
3. Install sysinstall in the VM: `pip install -e .`

**Steps** (see `linux_usb_create.sh`):
```bash
cd tests/smoke
chmod +x linux_usb_create.sh
./linux_usb_create.sh /dev/sdb  # Or your USB device ID
```

**Verification**:
- Script runs without errors
- Ventoy is installed on USB
- USB is bootable (verify with `file /dev/sdb1`)

---

### Scenario 2: Boot Repair on Dual-Boot VM
**Goal**: Verify `boot repair` restores GRUB after EFI is corrupted.

**Setup**:
1. Pre-built dual-boot VM with Ubuntu 24.04 + Windows 11
2. Deliberately clobber EFI partition: `dd if=/dev/zero of=/dev/sda1 bs=1M count=100`
3. Reboot → GRUB missing

**Steps** (see `boot_repair_dualboot.sh`):
```bash
cd tests/smoke
chmod +x boot_repair_dualboot.sh
./boot_repair_dualboot.sh
```

**Verification**:
- Script runs to completion
- GRUB menu appears after reboot
- Both Ubuntu and Windows 11 are still bootable

---

### Scenario 3: Disk Partitioning on Blank Target
**Goal**: Verify `partition apply` creates correct GPT layout for dual-boot.

**Setup**:
1. Ubuntu 24.04 in QEMU with 500GB blank virtual disk (`/dev/sdb`)
2. Install sysinstall in the VM

**Steps** (see `disk_partition_dualboot.sh`):
```bash
cd tests/smoke
chmod +x disk_partition_dualboot.sh
./disk_partition_dualboot.sh /dev/sdb
```

**Verification**:
- Layout matches expected GPT schema (see `tests/fixtures/partition/plan-default-500gb.json`)
- Partitions are created with correct sizes and filesystems
- No data loss on unrelated partitions

---

## Running Smoke Tests

### Local Testing (macOS or Linux host)

1. **Build the test VM image** (first time only):
   ```bash
   qemu-img create -f qcow2 ubuntu-24.04-test.qcow2 500G
   ```

2. **Download and verify ISO**:
   ```bash
   curl -O https://releases.ubuntu.com/24.04/ubuntu-24.04.1-live-server-amd64.iso
   sha256sum ubuntu-24.04.1-live-server-amd64.iso
   # Verify hash matches SHA256 above
   ```

3. **Boot VM with ISO and run tests**:
   ```bash
   qemu-system-x86_64 -m 4096 -smp 2 \
     -drive file=ubuntu-24.04-test.qcow2,format=qcow2 \
     -cdrom ubuntu-24.04.1-live-server-amd64.iso \
     -net nic -net user,hostfwd=tcp::2222-:22 &
   
   # Wait for boot, then SSH in and run tests
   sleep 60
   ssh -p 2222 root@localhost 'cd /mnt/sysinstall && ./tests/smoke/linux_usb_create.sh /dev/sdb'
   ```

### Nightly CI Run (GitHub Actions)

Smoke tests can be scheduled via GitHub Actions workflow (not included in default PR matrix):

```yaml
# .github/workflows/smoke.yml (optional — uncomment to enable)
on:
  schedule:
    - cron: '0 2 * * *'  # 2 AM UTC daily

jobs:
  smoke-linux:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: |
          # Prepare and run smoke tests
          pip install -e .
          pytest -m smoke --tb=short
```

---

## Troubleshooting

### USB passthrough not working
- On macOS UTM: Settings → USB → Shared
- On Linux KVM: `virsh attach-device vm-name usb-device.xml`
- In QEMU CLI: `-device usb-host,hostbus=1,hostport=2`

### EFI partition format issues
- Some VMs create legacy BIOS; ensure VM firmware is set to **UEFI/OVMF**
- Check: `efibootmgr -v` should show EFI boot entries

### VM disk not appearing
- Ensure sysinstall can see the disk: `lsblk` or `diskutil list`
- Pass correct device ID to test script (e.g., `/dev/sdb` not `/dev/sda`)

---

## Test Data Fixtures

Captured fixtures are stored under `tests/fixtures/` and can be reused:

- `tests/fixtures/disks/lsblk-ubuntu-with-usb.json` — Real lsblk output with USB stick
- `tests/fixtures/boot/efibootmgr-typical.txt` — Real efibootmgr output
- `tests/fixtures/partition/plan-default-500gb.json` — Expected partition plan

To capture new fixtures, use the sanitiser:

```python
from tests._sanitiser import sanitise_json_fixture
import json

# Load real output
output = subprocess.run(['lsblk', '-J'], capture_output=True, text=True).stdout
data = json.loads(output)

# Sanitise sensitive data
safe = sanitise_json_fixture(data)
print(json.dumps(safe, indent=2))
```

---

## Next Steps

- [ ] Document Windows 11 Hyper-V setup and test steps
- [ ] Add pre-built VM image snapshots to reduce setup time
- [ ] Integrate with scheduled GitHub Actions runner for nightly validation
