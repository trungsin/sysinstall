# Windows Code Signing Script
# Signs sysinstall.exe with Authenticode certificate
# No-op if SIGN_CERT_BASE64 is empty (unsigned MVP)

param(
    [string]$BinaryPath = "dist/sysinstall.exe",
    [string]$CertBase64 = $env:SIGN_CERT_BASE64,
    [string]$CertPassword = $env:SIGN_CERT_PASSWORD,
    [string]$TimestampUrl = $env:SIGN_TIMESTAMP_URL
)

$ErrorActionPreference = "Stop"

Write-Host "Windows Code Signing Script"
Write-Host "============================"

# Check if binary exists
if (-not (Test-Path $BinaryPath)) {
    Write-Error "Binary not found: $BinaryPath"
    exit 1
}

# Check if signing is configured
if ([string]::IsNullOrEmpty($CertBase64)) {
    Write-Host "SIGN_CERT_BASE64 not set. Skipping signing (unsigned MVP)."
    exit 0
}

Write-Host "Decoding certificate from base64..."
try {
    $certBytes = [System.Convert]::FromBase64String($CertBase64)
    $certPath = [System.IO.Path]::GetTempFileName()
    [System.IO.File]::WriteAllBytes($certPath, $certBytes)
    Write-Host "Certificate decoded to temporary file: $certPath"
}
catch {
    Write-Error "Failed to decode certificate: $_"
    exit 1
}

# Import certificate into local machine store
Write-Host "Importing certificate into local store..."
try {
    $cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2 `
        -ArgumentList @($certPath, $CertPassword, [System.Security.Cryptography.X509Certificates.X509KeyStorageFlags]::DefaultKeySet)
    Write-Host "Certificate imported: $($cert.Subject)"
}
catch {
    Write-Error "Failed to import certificate: $_"
    Remove-Item $certPath -Force
    exit 1
}

# Sign the executable with signtool
Write-Host "Signing binary: $BinaryPath"
try {
    if ([string]::IsNullOrEmpty($TimestampUrl)) {
        # Sign without timestamp (valid locally but no time proof)
        & signtool sign /f $certPath /p $CertPassword /fd SHA256 $BinaryPath
    }
    else {
        # Sign with timestamp (verifiable offline)
        & signtool sign /f $certPath /p $CertPassword /fd SHA256 /tr $TimestampUrl /td SHA256 $BinaryPath
    }

    if ($LASTEXITCODE -ne 0) {
        Write-Error "signtool failed with exit code: $LASTEXITCODE"
        Remove-Item $certPath -Force
        exit 1
    }

    Write-Host "Binary signed successfully: $BinaryPath"
}
catch {
    Write-Error "Failed to sign binary: $_"
    Remove-Item $certPath -Force
    exit 1
}

# Verify signature
Write-Host "Verifying signature..."
try {
    & signtool verify /pa $BinaryPath
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Signature verification failed"
        Remove-Item $certPath -Force
        exit 1
    }
    Write-Host "Signature verified successfully."
}
catch {
    Write-Error "Verification failed: $_"
    Remove-Item $certPath -Force
    exit 1
}

# Cleanup
Remove-Item $certPath -Force
Write-Host "Signing complete."
exit 0
