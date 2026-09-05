# start_web2api.ps1
# Starts and verifies gemini-web2api daemon on port 8081

$ErrorActionPreference = "SilentlyContinue"
$web2apiDir = Join-Path $PSScriptRoot "..\..\gemini-web2api"
if (-not (Test-Path $web2apiDir)) {
    # Fallback to absolute or Engine_1 path
    $web2apiDir = "c:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR\gemini-web2api"
}

$conn = Get-NetTCPConnection -LocalPort 8081 -ErrorAction SilentlyContinue
if ($conn) {
    Write-Host "[web2api] Service already listening on port 8081 (PID: $($conn.OwningProcess))."
} else {
    Write-Host "[web2api] Launching gemini-web2api daemon from $web2apiDir..."
    Start-Process -FilePath "python" -ArgumentList "gemini_web2api.py" -WorkingDirectory $web2apiDir -WindowStyle Hidden
    Start-Sleep -Seconds 3
    $conn = Get-NetTCPConnection -LocalPort 8081 -ErrorAction SilentlyContinue
    if ($conn) {
        Write-Host "[web2api] Successfully started on port 8081 (PID: $($conn.OwningProcess))."
    } else {
        Write-Warning "[web2api] Failed to bind to port 8081. Check logs in $web2apiDir."
        exit 1
    }
}

# Health Check
try {
    $resp = Invoke-RestMethod -Uri "http://localhost:8081/v1/models" -Headers @{ Authorization = "Bearer sk-gemini" } -TimeoutSec 10
    $modelCount = $resp.data.Count
    Write-Host "[web2api] Health check PASSED: $modelCount models available."
    exit 0
} catch {
    Write-Warning "[web2api] Health check request failed: $_"
    exit 1
}
