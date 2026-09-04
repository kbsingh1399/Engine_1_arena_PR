"""
web2api_multi_agent.py
-----------------------
Zero-Token Cost Parallel Multi-Agent Orchestrator powered by local gemini-web2api.
Runs specialized parallel agents (Quant Risk, Microstructure, Regime Strategy, QA Verification)
concurrently via http://localhost:8081 with zero paid API token spend.
"""

import sys
import io
import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any

# Force UTF-8 encoding across Windows console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

WEB2API_URL = "http://localhost:8081/v1/chat/completions"
API_KEY = "sk-gemini"
DEFAULT_MODEL = "gemini-3.7-flash"

def call_agent(agent_name: str, system_prompt: str, user_prompt: str, model: str = DEFAULT_MODEL, temperature: float = 0.2) -> Dict[str, Any]:
    """Invokes an individual agent via gemini-web2api."""
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": temperature
    }
    
    req = urllib.request.Request(WEB2API_URL, data=json.dumps(payload).encode('utf-8'), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            reply = data["choices"][0]["message"]["content"]
            return {"agent": agent_name, "status": "success", "response": reply}
    except Exception as e:
        return {"agent": agent_name, "status": "error", "error": str(e)}

def run_parallel_council(tasks: List[Dict[str, str]], max_workers: int = 4) -> Dict[str, str]:
    """
    Executes multiple agents in parallel.
    Each task dict must have: 'name', 'system', 'prompt', and optional 'model'.
    """
    results = {}
    print(f"\n[Parallel Council] Dispatching {len(tasks)} specialized agents concurrently via gemini-web2api...")
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(
                call_agent, 
                t["name"], 
                t["system"], 
                t["prompt"], 
                t.get("model", DEFAULT_MODEL)
            ): t["name"] for t in tasks
        }
        for future in as_completed(future_map):
            name = future_map[future]
            try:
                res = future.result()
                if res["status"] == "success":
                    print(f"  [+] Agent '{name}' completed successfully.")
                    results[name] = res["response"]
                else:
                    print(f"  [-] Agent '{name}' failed: {res.get('error')}")
                    results[name] = f"Error: {res.get('error')}"
            except Exception as e:
                print(f"  [-] Agent '{name}' exception: {e}")
                results[name] = f"Exception: {e}"
    return results

if __name__ == '__main__':
    # Quick health check if run standalone
    test_tasks = [
        {
            "name": "Quant-Risk-Auditor",
            "system": "You are a quantitative risk auditor. Be concise, rigorous, and mathematical.",
            "prompt": "Evaluate in 2 sentences why a 5R trailing stop with no breakeven ratchet fails on 15m crypto data."
        },
        {
            "name": "Microstructure-Specialist",
            "system": "You are a crypto microstructure specialist. Focus on order flow and CVD absorption.",
            "prompt": "Explain in 2 sentences why Spot CVD divergence is required before fading a liquidation spike."
        }
    ]
    outputs = run_parallel_council(test_tasks)
    for agent, text in outputs.items():
        print(f"\n=== {agent} Output ===")
        print(text)
