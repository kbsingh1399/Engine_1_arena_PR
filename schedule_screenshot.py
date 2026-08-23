import os
import time
import subprocess
from datetime import datetime, timedelta

def main():
    workspace_dir = r"c:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR"
    screenshot_path = os.path.join(workspace_dir, "screenshot_1.png")
    ps_script_path = os.path.join(workspace_dir, "take_screenshot.ps1")
    
    # 1. Delete the file if screenshot_1 exists before scheduling/taking
    if os.path.exists(screenshot_path):
        try:
            os.remove(screenshot_path)
            print(f"[PRE-CLEAN] Deleted existing file: {screenshot_path}")
        except Exception as e:
            print(f"[WARN] Failed to delete existing screenshot: {e}")
            
    # Remove error log if it exists
    err_log = os.path.join(workspace_dir, "screenshot_err.txt")
    if os.path.exists(err_log):
        try:
            os.remove(err_log)
        except Exception:
            pass

    # 2. Calculate the next second (e.g., current time + 2 seconds for safe scheduling buffer)
    now = datetime.now()
    trigger_time = now + timedelta(seconds=2)
    trigger_str = trigger_time.strftime("%Y-%m-%dT%H:%M:%S")
    
    print(f"Current Time: {now.strftime('%H:%M:%S')}")
    print(f"Scheduling Task for: {trigger_time.strftime('%H:%M:%S')}")

    # 3. Create the PowerShell command to register the task
    # We run it as the currently logged-in user in interactive logon mode so it has GUI access
    ps_cmd = f"""
    $Action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{ps_script_path}"'
    $Trigger = New-ScheduledTaskTrigger -Once -At "{trigger_str}"
    $Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\\$env:USERNAME" -LogonType Interactive
    Register-ScheduledTask -TaskName "ArenaScreenshotTask" -Action $Action -Trigger $Trigger -Principal $Principal -Force
    """
    
    # Execute the command
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            check=True
        )
        print("[SUCCESS] Scheduled task 'ArenaScreenshotTask' successfully created.")
        print(res.stdout.strip())
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Failed to schedule task: {e}")
        print(e.stderr)

if __name__ == "__main__":
    main()
