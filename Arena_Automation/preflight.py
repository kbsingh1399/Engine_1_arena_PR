import glob
import os
import subprocess
import sys
import time
import urllib.request


PORT = 19333
USER_DATA = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data_Arena")
CHROME_EXE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
URLS = [
    "https://arena.ai/c/01a020d1-e67f-773a-bd59-5c12837c9f71",
    "https://arena.ai/c/01a020d2-8eb9-783f-bb02-d5f2a42efcc6",
    "https://arena.ai/c/01a020d3-4b03-7312-a14f-5e7cd1fd79a9",
    "https://arena.ai/c/01a020d4-1d98-7b9a-9efd-bd70d60735e2",
    "https://arena.ai/c/01a020d5-492b-7ba0-8b9c-9cc38c79990f",
]


def is_cdp_alive() -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def kill_process_on_port(port: int) -> None:
    try:
        output = subprocess.check_output(f"netstat -ano | findstr :{port}", shell=True, text=True)
        for line in output.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.strip().split()
                if len(parts) >= 5:
                    pid = parts[-1]
                    print(f"Killing process {pid} on port {port}...")
                    subprocess.run(f"taskkill /F /PID {pid} /T", shell=True, capture_output=True)
    except subprocess.CalledProcessError:
        pass


def main() -> None:
    print("=" * 60)
    print("  ARENA.AI PRE-FLIGHT: Kill prior sessions")
    print("=" * 60)

    print("[1/4] Stopping any prior python arena scripts...")
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process | "
         "Where-Object { $_.CommandLine -like '*arena_ui_automation.py*' } | "
         "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"],
        capture_output=True,
    )
    time.sleep(0.5)

    print(f"[2/4] Killing stale Chrome strictly on port {PORT}...")
    kill_process_on_port(PORT)
    time.sleep(1)

    print("[3/4] Clearing Chrome singleton locks...")
    for lock in glob.glob(os.path.join(USER_DATA, "Singleton*")):
        try:
            os.remove(lock)
        except Exception:
            pass

    print("[3.5/4] Resetting Chrome crash flags in Preferences...")
    prefs_path = os.path.join(USER_DATA, "Default", "Preferences")
    if os.path.exists(prefs_path):
        try:
            import json
            with open(prefs_path, "r", encoding="utf-8") as f:
                prefs = json.load(f)
            if "profile" in prefs and "exit_type" in prefs["profile"]:
                prefs["profile"]["exit_type"] = "Normal"
            with open(prefs_path, "w", encoding="utf-8") as f:
                json.dump(prefs, f)
        except Exception as e:
            print(f"Warning: Could not reset exit_type in Preferences: {e}")

    print(f"[4/4] Launching Chrome with {len(URLS)} tabs in foreground...")
    subprocess.Popen(
        [CHROME_EXE, f"--remote-debugging-port={PORT}",
         f"--user-data-dir={USER_DATA}", "--start-maximized",
         "--hide-crash-restore-bubble", "--disable-session-crashed-bubble",
         "--no-first-run", "--no-default-browser-check"] + URLS,
        shell=False,
    )

    print("Waiting for Chrome CDP to be ready...")
    for i in range(1, 25):
        time.sleep(1)
        if is_cdp_alive():
            print(f"Chrome is ready after {i}s!")
            sys.exit(0)
        print(f"  ...waiting ({i}/24)")

    print("ERROR: Chrome did not become ready within 24 seconds.")
    sys.exit(1)


if __name__ == "__main__":
    main()
