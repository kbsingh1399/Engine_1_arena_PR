$scriptPath = "C:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR\run_arena_task.bat"
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$scriptPath`""
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName "ArenaAutomationTask" -Action $action -Principal $principal -Settings $settings -Force
Write-Output "SUCCESS: ArenaAutomationTask has been registered with Windows Task Scheduler."
