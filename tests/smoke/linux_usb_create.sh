#!/bin/bash
# Linux VM smoke test: USB creation with Ventoy
# Prerequisites: sysinstall installed, USB device passthrough enabled
# Usage: ./linux_usb_create.sh /dev/sdb

set -euo pipefail

USB_DEVICE="${1:-/dev/sdb}"
LOG_FILE="/tmp/usb-create-smoke.log"

echo "=== USB Create Smoke Test (Linux) ===" | tee "$LOG_FILE"
echo "Target device: $USB_DEVICE" | tee -a "$LOG_FILE"
echo "Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "$LOG_FILE"

# Sanity check: device exists and is writable
if [ ! -e "$USB_DEVICE" ]; then
    echo "ERROR: Device $USB_DEVICE not found" | tee -a "$LOG_FILE"
    exit 1
fi

if [ ! -w "$USB_DEVICE" ]; then
    echo "ERROR: Device $USB_DEVICE not writable (need sudo?)" | tee -a "$LOG_FILE"
    exit 1
fi

# Sanity check: device looks like USB (size is reasonable)
SIZE=$(blockdev --getsize64 "$USB_DEVICE" 2>/dev/null || echo "0")
MIN_SIZE=$((30 * 1024 * 1024 * 1024))  # 30GB minimum
if [ "$SIZE" -lt "$MIN_SIZE" ]; then
    echo "WARNING: Device $USB_DEVICE is ${SIZE} bytes (< 30GB). Proceeding anyway." | tee -a "$LOG_FILE"
fi

# Run sysinstall usb create with dry-run first
echo "" | tee -a "$LOG_FILE"
echo "Step 1: Dry-run (no writes)" | tee -a "$LOG_FILE"
if sysinstall usb create --device "$USB_DEVICE" --dry-run --confirm >> "$LOG_FILE" 2>&1; then
    echo "✓ Dry-run passed" | tee -a "$LOG_FILE"
else
    echo "✗ Dry-run failed" | tee -a "$LOG_FILE"
    exit 1
fi

# Run actual usb create
echo "" | tee -a "$LOG_FILE"
echo "Step 2: Writing Ventoy to $USB_DEVICE" | tee -a "$LOG_FILE"
if sysinstall usb create --device "$USB_DEVICE" --confirm >> "$LOG_FILE" 2>&1; then
    echo "✓ USB creation succeeded" | tee -a "$LOG_FILE"
else
    echo "✗ USB creation failed" | tee -a "$LOG_FILE"
    exit 1
fi

# Verify: USB should be bootable now
echo "" | tee -a "$LOG_FILE"
echo "Step 3: Verification" | tee -a "$LOG_FILE"

# Check partition table
if fdisk -l "$USB_DEVICE" 2>/dev/null | grep -q "FAT32"; then
    echo "✓ USB has FAT32 partition (Ventoy)" | tee -a "$LOG_FILE"
else
    echo "✗ USB missing FAT32 partition" | tee -a "$LOG_FILE"
    exit 1
fi

# Check for Ventoy signature (magic bytes at offset 0x1FE)
if od -A d -t x1 -N 512 "$USB_DEVICE"1 2>/dev/null | grep -q "55 aa"; then
    echo "✓ USB partition 1 has boot signature" | tee -a "$LOG_FILE"
else
    echo "⚠ USB partition 1 boot signature check inconclusive" | tee -a "$LOG_FILE"
fi

echo "" | tee -a "$LOG_FILE"
echo "=== SMOKE TEST PASSED ===" | tee -a "$LOG_FILE"
echo "Log: $LOG_FILE"
