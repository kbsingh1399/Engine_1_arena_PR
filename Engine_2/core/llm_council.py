"""
Engine_2/core/llm_council.py
Unified dual-router for Real-Time Execution (OpenRouter) & Deep Research (NVIDIA NIM).
"""
import os
import requests
import json
import logging

logger = logging.getLogger(__name__)

OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")
NVIDIA_NIM_KEY = os.getenv("NVIDIA_API_KEY", "")

def query_fast_advisor(prompt: str, model: str = "openai/gpt-4o-mini", timeout: int = 15) -> str:
    """
    Sub-second live gating & trade confirmation via OpenRouter.
    Suitable for real-time confirmation in live monitors or fast post-window diagnostics.
    """
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1000,
        "temperature": 0.2
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"]
        else:
            logger.warning(f"[LLM_COUNCIL] OpenRouter error {resp.status_code}: {resp.text[:200]}")
            return f"Error: {resp.status_code}"
    except Exception as e:
        logger.warning(f"[LLM_COUNCIL] OpenRouter connection exception: {e}")
        return f"Exception: {e}"

def query_deep_reasoner(prompt: str, model: str = "moonshotai/kimi-k3", timeout: int = 60) -> str:
    """
    Deep 1M-context reasoning & macro-regime modeling via NVIDIA NIM.
    Suitable for batch synthesis of multi-year liquidation logs or forensic trade post-mortems.
    """
    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {NVIDIA_NIM_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 4096,
        "temperature": 0.6,
        "stream": False
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"]
        else:
            logger.warning(f"[LLM_COUNCIL] NVIDIA NIM error {resp.status_code}: {resp.text[:200]}")
            return f"Error: {resp.status_code}"
    except Exception as e:
        logger.warning(f"[LLM_COUNCIL] NVIDIA NIM connection exception: {e}")
        return f"Exception: {e}"
