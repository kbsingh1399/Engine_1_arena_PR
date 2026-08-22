@echo off
setlocal
cd /d "%~dp0"

set "PY=C:\Users\SIGMA\AppData\Local\Python\pythoncore-3.14-64\python.exe"

echo ======================================================================
echo              ARENA.AI MULTI-MODEL INTERACTIVE LAUNCHER
echo ======================================================================
echo.

echo [Step 1/2] Pre-flight: killing prior sessions, launching Chrome...
"%PY%" preflight.py
if %ERRORLEVEL% neq 0 (
    echo.
    echo ERROR: Pre-flight failed. Chrome did not start.
    pause
    exit /b 1
)

echo.
echo [Step 2/2] Submitting prompts across all 5 models...
"%PY%" arena_ui_automation.py --files six_strategy_engine.py binance_broker.py live_unified_predictor.py --prompt arena_prompt.txt

echo.
echo ======================================================================
echo Done! Report saved to: arena_latest_copied_response.txt
echo ======================================================================
pause
