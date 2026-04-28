# Windows VM smoke test: USB creation with Ventoy
# Prerequisites: sysinstall installed, USB device passthrough enabled
# Usage: .\windows_usb_create.ps1 -DiskNumber 1

param(
    [int]$DiskNumber = 1,
    [string]$LogFile = "C:\tmp\usb-create-smoke.log"
)

$ErrorActionPreference = "Stop"

# Helper: Write to log and console
function Log {
    param([string]$Message)
    Write-Host $Message
    Add-Content -Path $LogFile -Value $Message
}

# Create log directory
$LogDir = Split-Path $LogFile
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

Log "=== USB Create Smoke Test (Windows) ==="
Log "Target disk: Disk $DiskNumber"
Log "Timestamp: $(Get-Date -Format 'yyyy-MM-ddTHH:mm:ssZ')"
Log ""

# Sanity check: disk exists
try {
    $Disk = Get-Disk -Number $DiskNumber -ErrorAction Stop
} catch {
    Log "ERROR: Disk $DiskNumber not found"
    exit 1
}

Log "Disk found: $($Disk.FriendlyName), Size: $([math]::Round($Disk.Size / 1GB, 2)) GB"

# Sanity check: disk is at least 30GB
$MinSize = 30GB
if ($Disk.Size -lt $MinSize) {
    Log "WARNING: Disk is smaller than 30GB. Proceeding anyway."
}

# Sanity check: disk has no critical system partitions
if ($Disk.IsBoot -or $Disk.IsSystem) {
    Log "ERROR: Disk is marked as Boot or System disk. Refusing to write."
    exit 1
}

Log ""
Log "Step 1: Dry-run (no writes)"
try {
    & sysinstall usb create --device disk$DiskNumber --dry-run --confirm 2>&1 | Tee-Object -FilePath $LogFile -Append | Out-Null
    Log "✓ Dry-run passed"
} catch {
    Log "✗ Dry-run failed: $_"
    exit 1
}

Log ""
Log "Step 2: Writing Ventoy to Disk $DiskNumber"
try {
    & sysinstall usb create --device disk$DiskNumber --confirm 2>&1 | Tee-Object -FilePath $LogFile -Append | Out-Null
    Log "✓ USB creation succeeded"
} catch {
    Log "✗ USB creation failed: $_"
    exit 1
}

Log ""
Log "Step 3: Verification"

# Refresh disk list to see new partitions
Update-HostStorageCache

# Check that disk now has partitions
$Partitions = Get-Partition -DiskNumber $DiskNumber -ErrorAction SilentlyContinue
if ($Partitions.Count -gt 0) {
    Log "✓ Disk $DiskNumber has $($Partitions.Count) partition(s)"
} else {
    Log "✗ Disk $DiskNumber has no partitions"
    exit 1
}

# Check for FAT32 (Ventoy partition)
$FatPartition = $Partitions | Where-Object { $_.Type -like "*FAT*" }
if ($FatPartition) {
    Log "✓ Found FAT32 partition (Ventoy)"
} else {
    Log "✗ No FAT32 partition found"
    exit 1
}

# Check partition size is reasonable (at least 128MB)
if ($FatPartition.Size -ge 128MB) {
    Log "✓ Ventoy partition size: $([math]::Round($FatPartition.Size / MB, 2)) MB"
} else {
    Log "✗ Ventoy partition too small: $([math]::Round($FatPartition.Size / MB, 2)) MB"
    exit 1
}

Log ""
Log "=== SMOKE TEST PASSED ==="
Log "Log: $LogFile"
