$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = "cmd.exe"
$psi.Arguments = "/k run_engine_autonomous.bat"
$psi.WorkingDirectory = "C:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR"
$psi.UseShellExecute = $true
$psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Normal
$proc = [System.Diagnostics.Process]::Start($psi)
Write-Output "GUI_PROCESS_STARTED_PID: $($proc.Id)"
