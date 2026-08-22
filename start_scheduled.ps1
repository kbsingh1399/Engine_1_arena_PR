$TaskName = 'Engine1_LiveConsole_Launch'
$Action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-ExecutionPolicy Bypass -WindowStyle Hidden -File "C:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR\launch_visible.ps1"'
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddSeconds(5)
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Force
Start-ScheduledTask -TaskName $TaskName
