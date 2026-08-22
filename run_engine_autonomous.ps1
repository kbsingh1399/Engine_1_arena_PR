# Engine 1 - Autonomous Live Trading Engine Runner
# Suppresses all Windows pause prompts and ensures infinite auto-restart loop

Set-Location "C:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR"
$env:PYTHONUNBUFFERED = "1"
$env:PYTHONIOENCODING = "utf-8"

$pythonExe = "C:\Users\SIGMA\AppData\Local\Python\pythoncore-3.14-64\python.exe"
if (-not (Test-Path $pythonExe)) { $pythonExe = "python" }

$chromeExe = "C:\Program Files\Google\Chrome\Application\chrome.exe"
if (-not (Test-Path $chromeExe)) { $chromeExe = "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" }

while ($true) {
    Clear-Host
    Write-Output "====================================================================="
    Write-Output " Engine 1 Autonomous Live Execution (Auto-Restart Watchdog Active)"
    Write-Output (" Directory: " + (Get-Location).Path)
    Write-Output " Log File: live_engine_output.txt"
    Write-Output (" Timestamp: " + (Get-Date).ToString("yyyy-MM-dd HH:mm:ss"))
    Write-Output "====================================================================="

    # Pre-startup process and lock cleanup
    Get-Process chrome -ErrorAction SilentlyContinue | Stop-Process -Force
    Get-CimInstance Win32_Process -Filter "name = 'python.exe'" | Where-Object { 
        $_.CommandLine -notlike '*code_review_graph*' -and 
        $_.CommandLine -notlike '*antigravity*' -and 
        ($_.CommandLine -like '*Engine_1.py*' -or $_.CommandLine -like '*train_six_strategy*') 
    } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

    # Clean stale Singleton lock files
    @("chrome_profile_tab1\SingletonLock", "chrome_profile_tab1\SingletonSocket", "chrome_profile_tab1\lockfile",
      "chrome_profile_tab2\SingletonLock", "chrome_profile_tab2\SingletonSocket", "chrome_profile_tab2\lockfile") | ForEach-Object {
        if (Test-Path $_) { Remove-Item -Path $_ -Force -ErrorAction SilentlyContinue }
    }

    # Pre-launch visible Chrome GUI windows on interactive desktop
    Write-Output "[LAUNCHER] Opening visible Google Chrome windows in foreground..."
    if (Test-Path $chromeExe) {
        Start-Process -FilePath $chromeExe -ArgumentList "--remote-debugging-port=9222", "--remote-allow-origins=*", "--start-maximized", "--user-data-dir=`"$((Get-Location).Path)\chrome_profile_tab1`"", "https://www.coinglass.com/login"
        Start-Process -FilePath $chromeExe -ArgumentList "--remote-debugging-port=19900", "--remote-allow-origins=*", "--start-maximized", "--user-data-dir=`"$((Get-Location).Path)\chrome_profile_tab2`"", "https://www.coinglass.com/login"
    }
    Start-Sleep -Seconds 3

    # Execute Engine_1
    & $pythonExe -u Engine_1.py

    Write-Output ""
    Write-Output "====================================================================="
    Write-Output " [WATCHDOG] Engine exited. Relaunching in 5 seconds..."
    Write-Output "====================================================================="
    Start-Sleep -Seconds 5
}
