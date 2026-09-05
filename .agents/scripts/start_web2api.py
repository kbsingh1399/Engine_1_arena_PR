"""
start_web2api.py
----------------
Starts and verifies gemini-web2api background daemon on port 8081.
"""

import sys
import os
import time
import subprocess
import urllib.request
import json

def is_port_listening(url="http://localhost:8081/v1/models"):
    req = urllib.request.Request(url, headers={"Authorization": "Bearer sk-gemini"})
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return True, len(data.get("data", []))
    except Exception:
        return False, 0

def start_daemon():
    listening, count = is_port_listening()
    if listening:
        print(f"[web2api] Already active on port 8081 ({count} models available).")
        return True

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    web2api_dir = os.path.join(repo_root, "gemini-web2api")
    script_path = os.path.join(web2api_dir, "gemini_web2api.py")

    if not os.path.exists(script_path):
        # Fallback to Engine_1 root
        web2api_dir = r"c:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR\gemini-web2api"
        script_path = os.path.join(web2api_dir, "gemini_web2api.py")

    print(f"[web2api] Starting background process: {script_path}")
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    subprocess.Popen(
        [sys.executable, "gemini_web2api.py"],
        cwd=web2api_dir,
        creationflags=creationflags,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    for attempt in range(10):
        time.sleep(1)
        listening, count = is_port_listening()
        if listening:
            print(f"[web2api] Successfully bound to port 8081 ({count} models ready).")
            return True

    print("[web2api] ERROR: Timed out waiting for gemini-web2api to listen on port 8081.")
    return False

if __name__ == "__main__":
    success = start_daemon()
    sys.exit(0 if success else 1)
