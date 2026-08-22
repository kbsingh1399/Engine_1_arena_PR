# Kill Engine 1 python process and the visible terminal window
$pythonProcs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'Engine_1\.py' -and $_.Name -match 'python' }
if ($pythonProcs) {
    foreach ($p in $pythonProcs) {
        Write-Host "Killing Python Engine Process PID: $($p.ProcessId)"
        Stop-Process -Id $p.ProcessId -Force
    }
}

$cmdProcs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'run_engine_autonomous\.bat' -and $_.Name -match 'cmd' }
if ($cmdProcs) {
    foreach ($p in $cmdProcs) {
        Write-Host "Killing Visible Terminal Process PID: $($p.ProcessId)"
        Stop-Process -Id $p.ProcessId -Force
    }
    Write-Host "Visible terminal killed."
} else {
    Write-Host "No visible terminal running run_engine_autonomous.bat found."
}
