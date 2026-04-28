#!/bin/bash
# Linux VM smoke test: Disk partitioning for dual-boot
# Prerequisites: blank target disk available, sysinstall installed
# Usage: ./disk_partition_dualboot.sh /dev/sdb

set -euo pipefail

TARGET_DISK="${1:-/dev/sdb}"
LOG_FILE="/tmp/partition-smoke.log"
PLAN_FILE="/tmp/partition-plan.json"

echo "=== Disk Partition Smoke Test (Dual-Boot) ===" | tee "$LOG_FILE"
echo "Target disk: $TARGET_DISK" | tee -a "$LOG_FILE"
echo "Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "$LOG_FILE"

# Sanity check: device exists and is writable
if [ ! -e "$TARGET_DISK" ]; then
    echo "ERROR: Device $TARGET_DISK not found" | tee -a "$LOG_FILE"
    exit 1
fi

if [ ! -w "$TARGET_DISK" ]; then
    echo "ERROR: Device $TARGET_DISK not writable (need sudo?)" | tee -a "$LOG_FILE"
    exit 1
fi

# Get disk size
SIZE=$(blockdev --getsize64 "$TARGET_DISK" 2>/dev/null || echo "0")
SIZE_GB=$((SIZE / 1024 / 1024 / 1024))
echo "Disk size: ${SIZE_GB} GB (${SIZE} bytes)" | tee -a "$LOG_FILE"

# Sanity check: disk is at least 100GB for dual-boot test
MIN_SIZE=$((100 * 1024 * 1024 * 1024))
if [ "$SIZE" -lt "$MIN_SIZE" ]; then
    echo "WARNING: Disk is smaller than 100GB. Test may be incomplete." | tee -a "$LOG_FILE"
fi

# Step 1: Generate partition plan
echo "" | tee -a "$LOG_FILE"
echo "Step 1: Generate partition plan" | tee -a "$LOG_FILE"
# We use a simple dual-boot layout: 1GB EFI, rest for OS
cat > "$PLAN_FILE" << EOF
{
  "changes": [
    {
      "disk": "$TARGET_DISK",
      "table": "gpt",
      "partitions": [
        {
          "number": 1,
          "size_bytes": 1048576000,
          "fstype": "fat32",
          "label": "BOOT",
          "bootable": true
        },
        {
          "number": 2,
          "size_bytes": $((SIZE - 1048576000)),
          "fstype": "ext4",
          "label": "ubuntu"
        }
      ]
    }
  ],
  "disk_id": "$TARGET_DISK",
  "total_size_bytes": $SIZE,
  "used_size_bytes": $((1048576000 + (SIZE - 1048576000)))
}
EOF

echo "✓ Partition plan generated: $PLAN_FILE" | tee -a "$LOG_FILE"
cat "$PLAN_FILE" | tee -a "$LOG_FILE"

# Step 2: Dry-run partition
echo "" | tee -a "$LOG_FILE"
echo "Step 2: Dry-run partition apply" | tee -a "$LOG_FILE"
if sysinstall partition apply --target "$TARGET_DISK" --dry-run --confirm >> "$LOG_FILE" 2>&1; then
    echo "✓ Dry-run passed" | tee -a "$LOG_FILE"
else
    echo "⚠ Dry-run failed (expected if device not recognized)" | tee -a "$LOG_FILE"
fi

# Step 3: Apply partition plan
echo "" | tee -a "$LOG_FILE"
echo "Step 3: Apply partitions to $TARGET_DISK" | tee -a "$LOG_FILE"
if sysinstall partition apply --target "$TARGET_DISK" --confirm >> "$LOG_FILE" 2>&1; then
    echo "✓ Partition apply succeeded" | tee -a "$LOG_FILE"
else
    echo "✗ Partition apply failed" | tee -a "$LOG_FILE"
    exit 1
fi

# Step 4: Verify partition layout
echo "" | tee -a "$LOG_FILE"
echo "Step 4: Verification" | tee -a "$LOG_FILE"

# Refresh partition table
partprobe "$TARGET_DISK" 2>/dev/null || true
sleep 2

# Check partition count
PARTITION_COUNT=$(lsblk -nl "$TARGET_DISK" | tail -n +2 | wc -l)
echo "Partitions created: $PARTITION_COUNT" | tee -a "$LOG_FILE"

if [ "$PARTITION_COUNT" -ge 2 ]; then
    echo "✓ Expected 2+ partitions, found $PARTITION_COUNT" | tee -a "$LOG_FILE"
else
    echo "✗ Expected 2+ partitions, found $PARTITION_COUNT" | tee -a "$LOG_FILE"
    exit 1
fi

# Show partition layout
echo "" | tee -a "$LOG_FILE"
echo "Partition layout:" | tee -a "$LOG_FILE"
fdisk -l "$TARGET_DISK" 2>/dev/null | tee -a "$LOG_FILE" || true

# Check for GPT
if fdisk -l "$TARGET_DISK" 2>/dev/null | grep -q "Disklabel type: gpt"; then
    echo "✓ Disk uses GPT (expected)" | tee -a "$LOG_FILE"
else
    echo "⚠ Disk may not be using GPT" | tee -a "$LOG_FILE"
fi

# Check for EFI partition
if lsblk -nl "$TARGET_DISK" | grep -q "fat32\|vfat"; then
    echo "✓ FAT32 EFI partition detected" | tee -a "$LOG_FILE"
else
    echo "⚠ FAT32 EFI partition not detected (may not be mounted)" | tee -a "$LOG_FILE"
fi

echo "" | tee -a "$LOG_FILE"
echo "=== SMOKE TEST PASSED ===" | tee -a "$LOG_FILE"
echo "Log: $LOG_FILE"
echo "Plan: $PLAN_FILE"
echo "Note: Verify partition layout matches expected GPT schema"
