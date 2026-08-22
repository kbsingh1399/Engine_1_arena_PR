@echo off
echo Triggering ArenaAutomationTask via Windows Task Scheduler...
schtasks /Run /TN "ArenaAutomationTask"
if %ERRORLEVEL% equ 0 (
    echo [OK] Interactive task triggered successfully in your desktop session.
) else (
    echo [ERROR] Could not trigger task. Ensure ArenaAutomationTask is registered.
)
