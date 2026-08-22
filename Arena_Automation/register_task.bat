@echo off
setlocal

set "SCRIPT_PATH=C:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR\Arena_Automation\run_arena_task.bat"

echo Registering ArenaAutomationTask in Windows Task Scheduler...
schtasks /Create /TN "ArenaAutomationTask" /TR "\"%SCRIPT_PATH%\"" /SC ONCE /ST 00:00 /F /IT

if %ERRORLEVEL% equ 0 (
    echo [SUCCESS] Task 'ArenaAutomationTask' registered successfully.
    echo You or the agent can trigger it anytime via:
    echo   schtasks /Run /TN "ArenaAutomationTask"
) else (
    echo [ERROR] Failed to register task.
)

exit /b 0
