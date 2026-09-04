"""
deepseek_harness_runner.py
--------------------------
Unified programmatic runner and evaluation bridge for DeepSeek Harness.
Enables launching DeepSeek Harness headless evaluations, web UI, or custom profile
agents directly from Python scripts or CLI.
"""

import sys
import os
import io
import subprocess
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

HARNESS_ROOT = Path(r"c:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR\deepseek-harness")

def run_dsh_headless(task_prompt: str, profile: str = "headless") -> str:
    """Runs a single evaluation task through DeepSeek Harness headless profile."""
    if not HARNESS_ROOT.exists():
        return f"Error: DeepSeek Harness not found at {HARNESS_ROOT}"
        
    cmd = ["pnpm", "run", "dsh", "--", f"--profile", profile, task_prompt]
    print(f"[DeepSeek Harness] Executing headless task: '{task_prompt}'")
    try:
        res = subprocess.run(
            cmd,
            cwd=str(HARNESS_ROOT),
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=180
        )
        if res.returncode == 0:
            print("[DeepSeek Harness] Execution completed successfully.")
            return res.stdout
        else:
            print(f"[DeepSeek Harness] Exited with code {res.returncode}")
            return f"Error ({res.returncode}):\nSTDOUT: {res.stdout}\nSTDERR: {res.stderr}"
    except Exception as e:
        return f"Exception during DeepSeek Harness execution: {e}"

def start_dsh_web(port: int = 3000):
    """Starts the DeepSeek Harness interactive web UI in the background."""
    print(f"[DeepSeek Harness] Launching Web UI at port {port}...")
    cmd = ["pnpm", "run", "dsh", "--", "web", "--port", str(port)]
    proc = subprocess.Popen(cmd, cwd=str(HARNESS_ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    print(f"[DeepSeek Harness] Web UI daemon launched with PID {proc.pid}")
    return proc.pid

if __name__ == '__main__':
    prompt = sys.argv[1] if len(sys.argv) > 1 else "--dump-default-config"
    if prompt in ["--dump-config", "--dump-default-config", "--version", "--help"]:
        cmd = ["pnpm", "run", "dsh", "--", prompt]
        subprocess.run(cmd, cwd=str(HARNESS_ROOT))
    else:
        output = run_dsh_headless(prompt)
        print(output)
