#!/bin/bash
set -euo pipefail

# macOS Code Signing & Notarization Script
# Signs sysinstall binary with Developer ID and notarizes with Apple
# No-op if APPLE_ID is empty (unsigned MVP)

BINARY_PATH="${1:-dist/sysinstall}"
APPLE_ID="${APPLE_ID:-}"
APP_PASSWORD="${APP_PASSWORD:-}"
TEAM_ID="${TEAM_ID:-}"

echo "macOS Code Signing & Notarization"
echo "=================================="

# Check if binary exists
if [[ ! -f "$BINARY_PATH" ]]; then
    echo "Error: Binary not found: $BINARY_PATH"
    exit 1
fi

# Check if signing is configured
if [[ -z "$APPLE_ID" ]] || [[ -z "$APP_PASSWORD" ]] || [[ -z "$TEAM_ID" ]]; then
    echo "APPLE_ID, APP_PASSWORD, or TEAM_ID not set. Skipping signing (unsigned MVP)."
    exit 0
fi

echo "Binary: $BINARY_PATH"
echo "Apple ID: $APPLE_ID"
echo "Team ID: $TEAM_ID"

# Create entitlements plist
ENTITLEMENTS_FILE=$(mktemp /tmp/entitlements.plist.XXXXXX)
cat > "$ENTITLEMENTS_FILE" << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>com.apple.security.cs.allow-unsigned-executable-memory</key>
  <true/>
  <key>com.apple.security.cs.allow-jit</key>
  <true/>
</dict>
</plist>
EOF

echo "Entitlements plist created: $ENTITLEMENTS_FILE"

# Step 1: Code sign the binary
echo "Step 1: Code signing binary..."
codesign --force \
         --sign "Developer ID Application: $APPLE_ID ($TEAM_ID)" \
         --options runtime \
         --entitlements "$ENTITLEMENTS_FILE" \
         --timestamp \
         "$BINARY_PATH"

if [[ $? -eq 0 ]]; then
    echo "✓ Binary signed successfully"
else
    echo "Error: Code signing failed"
    rm -f "$ENTITLEMENTS_FILE"
    exit 1
fi

# Verify signature
echo "Verifying signature..."
codesign --verify --verbose "$BINARY_PATH"
if [[ $? -eq 0 ]]; then
    echo "✓ Signature verified"
else
    echo "Warning: Signature verification failed"
fi

# Step 2: Create ZIP for notarization
echo "Step 2: Creating ZIP for notarization..."
BINARY_NAME=$(basename "$BINARY_PATH")
ZIP_FILE="/tmp/${BINARY_NAME}.zip"
ditto -c -k --keepParent "$BINARY_PATH" "$ZIP_FILE"
echo "✓ ZIP created: $ZIP_FILE"

# Step 3: Submit for notarization
echo "Step 3: Submitting for notarization..."
NOTARY_OUTPUT=$(xcrun notarytool submit "$ZIP_FILE" \
                  --apple-id "$APPLE_ID" \
                  --team-id "$TEAM_ID" \
                  --password "$APP_PASSWORD" \
                  --wait 2>&1)

echo "$NOTARY_OUTPUT"

# Extract notarization status
if echo "$NOTARY_OUTPUT" | grep -q "Accepted"; then
    echo "✓ Notarization accepted"
elif echo "$NOTARY_OUTPUT" | grep -q "In Progress"; then
    echo "Notarization still processing; check status via:"
    # Extract request ID from output
    REQUEST_ID=$(echo "$NOTARY_OUTPUT" | grep "id:" | awk '{print $NF}')
    echo "xcrun notarytool info $REQUEST_ID --apple-id $APPLE_ID --team-id $TEAM_ID --password $APP_PASSWORD"
else
    echo "Error: Notarization failed"
    echo "Full output:"
    echo "$NOTARY_OUTPUT"
    rm -f "$ENTITLEMENTS_FILE" "$ZIP_FILE"
    exit 1
fi

# Step 4: Staple notarization ticket (optional for raw binary; harmless)
echo "Step 4: Stapling notarization ticket..."
xcrun stapler staple "$BINARY_PATH" || echo "Warning: Stapling failed (may not be necessary for raw binary)"

# Cleanup
rm -f "$ENTITLEMENTS_FILE" "$ZIP_FILE"

echo ""
echo "✓ Code signing and notarization complete"
echo "Binary is ready for distribution: $BINARY_PATH"
exit 0
