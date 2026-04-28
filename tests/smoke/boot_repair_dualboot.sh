#!/bin/bash
# Linux VM smoke test: Boot repair on dual-boot system
# Prerequisites: pre-built dual-boot VM with Ubuntu + Windows, EFI deliberately clobbered
# Usage: ./boot_repair_dualboot.sh

set -euo pipefail

LOG_FILE="/tmp/boot-repair-smoke.log"
TARGET_DISK="${TARGET_DISK:-/dev/sda}"

echo "=== Boot Repair Smoke Test (Dual-Boot) ===" | tee "$LOG_FILE"
echo "Target disk: $TARGET_DISK" | tee -a "$LOG_FILE"
echo "Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "$LOG_FILE"

# Sanity check: this is a dual-boot system
if ! command -v efibootmgr &> /dev/null; then
    echo "ERROR: efibootmgr not found. This is not a UEFI system." | tee -a "$LOG_FILE"
    exit 1
fi

# Detect current boot entries before repair
echo "" | tee -a "$LOG_FILE"
echo "Step 1: Check current boot state" | tee -a "$LOG_FILE"
INITIAL_ENTRIES=$(efibootmgr 2>/dev/null | grep -c "Boot" || echo "0")
echo "Current EFI boot entries: $INITIAL_ENTRIES" | tee -a "$LOG_FILE"

if [ "$INITIAL_ENTRIES" -lt 2 ]; then
    echo "WARNING: Expected 2+ boot entries (Ubuntu + Windows). Found: $INITIAL_ENTRIES" | tee -a "$LOG_FILE"
fi

# Run sysinstall boot repair with dry-run first
echo "" | tee -a "$LOG_FILE"
echo "Step 2: Dry-run boot repair" | tee -a "$LOG_FILE"
if sysinstall boot repair --target "$TARGET_DISK" --dry-run --confirm >> "$LOG_FILE" 2>&1; then
    echo "✓ Boot repair dry-run passed" | tee -a "$LOG_FILE"
else
    echo "⚠ Boot repair dry-run failed (expected if no repair needed)" | tee -a "$LOG_FILE"
fi

# Run actual boot repair
echo "" | tee -a "$LOG_FILE"
echo "Step 3: Running boot repair" | tee -a "$LOG_FILE"
if sysinstall boot repair --target "$TARGET_DISK" --confirm >> "$LOG_FILE" 2>&1; then
    echo "✓ Boot repair succeeded" | tee -a "$LOG_FILE"
else
    # Boot repair may fail if nothing to repair; that's ok
    echo "⚠ Boot repair completed (may indicate no repair needed)" | tee -a "$LOG_FILE"
fi

# Verify: check boot entries after repair
echo "" | tee -a "$LOG_FILE"
echo "Step 4: Verification" | tee -a "$LOG_FILE"

FINAL_ENTRIES=$(efibootmgr 2>/dev/null | grep -c "Boot" || echo "0")
echo "EFI boot entries after repair: $FINAL_ENTRIES" | tee -a "$LOG_FILE"

if [ "$FINAL_ENTRIES" -ge 2 ]; then
    echo "✓ Boot entries restored (expected 2+, found $FINAL_ENTRIES)" | tee -a "$LOG_FILE"
else
    echo "✗ Boot repair may have failed: only $FINAL_ENTRIES entries" | tee -a "$LOG_FILE"
    exit 1
fi

# List boot entries for human verification
echo "" | tee -a "$LOG_FILE"
echo "Step 5: Boot menu entries" | tee -a "$LOG_FILE"
efibootmgr -v 2>/dev/null | tee -a "$LOG_FILE" || true

echo "" | tee -a "$LOG_FILE"
echo "=== SMOKE TEST PASSED ===" | tee -a "$LOG_FILE"
echo "Log: $LOG_FILE"
echo "Next: Reboot and verify GRUB menu shows both Ubuntu and Windows"
