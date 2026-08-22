# Restart Engine 1 by killing the python process
# The run_engine_autonomous.bat will automatically relaunch it
$processes = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'Engine_1\.py' -and $_.Name -match 'python' }

if ($processes) {
    foreach ($p in $processes) {
        Write-Host "Killing Python Engine Process PID: $($p.ProcessId)"
        Stop-Process -Id $p.ProcessId -Force
    }
    Write-Host "Engine killed. It will be automatically restarted by run_engine_autonomous.bat in 5 seconds."
} else {
    Write-Host "No running Engine_1.py process found."
}
