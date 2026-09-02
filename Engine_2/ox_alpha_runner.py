"""
Ox Alpha / GLM 5.3 Flash Autonomous Runner
Connects directly to OpenRouter using your verified key to solve the 20/20 OOS conquest.
"""

import os
import sys
from openai import OpenAI

API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
MODEL = "z-ai/glm-5.3-flash"

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=API_KEY,
)

def run_mission():
    mission_file = os.path.join(os.path.dirname(__file__), "AUTOCLAW_GLM5_3_HANDOFF_MISSION.md")
    if os.path.exists(mission_file):
        with open(mission_file, "r", encoding="utf-8") as f:
            mission_text = f.read()
    else:
        mission_text = "Conquer all 20 Out-Of-Sample walk-forward windows under strict zero-lookahead rules."

    print(f"[*] Starting Ox Alpha / GLM 5.3 Flash runner...")
    print(f"[*] Model: {MODEL}")
    print(f"[*] Sending mission prompt to OpenRouter...\n" + "="*80 + "\n")

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are the Lead Quantitative Architect and Trading Systems Engineer. "
                    "You are working directly on Engine 2 to achieve a 20/20 Out-Of-Sample walk-forward pass. "
                    "All code and proposals must adhere strictly to zero-lookahead, causal intra-bar execution, "
                    "and 18-month purged in-sample training. Be specific, mathematical, and actionable."
                )
            },
            {
                "role": "user",
                "content": mission_text
            }
        ],
        stream=True
    )

    for chunk in response:
        content = chunk.choices[0].delta.content
        if content:
            sys.stdout.write(content)
            sys.stdout.flush()
    print("\n" + "="*80 + "\n[*] Mission response complete.")

if __name__ == "__main__":
    run_mission()
