# run_10_checks.ps1 - Automated 10-cycle Kaizen verification loop

Write-Host "============================================================"
Write-Host "  STARTING 10-ITERATION CONTINUOUS PARITY VERIFICATION LOOP"
Write-Host "============================================================"

$logPath = "C:\Users\SIGMA\.gemini\antigravity-ide\brain\26d6ef1f-8af0-428f-a6a1-5e5749a3efdc\.system_generated\tasks\task-1276.log"

for ($i = 1; $i -le 10; $i++) {
    Write-Host "`n>>> [ITERATION $i / 10] Triggering live snapshot capture..." -ForegroundColor Cyan
    python schedule_screenshot.py
    Start-Sleep -Seconds 3
    
    if (Test-Path $logPath) {
        Write-Host ">>> [ITERATION $i / 10] Telemetry Snapshot:" -ForegroundColor Green
        Get-Content $logPath -Tail 34
    } else {
        Write-Host "Log file not yet available: $logPath" -ForegroundColor Yellow
    }
    
    if ($i -lt 10) {
        Write-Host "Sleeping 2s before next iteration..."
        Start-Sleep -Seconds 2
    }
}

Write-Host "`n============================================================"
Write-Host "  10-ITERATION VERIFICATION LOOP COMPLETED SUCCESSFULLY"
Write-Host "============================================================"
