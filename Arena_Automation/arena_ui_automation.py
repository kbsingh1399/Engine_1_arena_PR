#!/usr/bin/env python3
"""
arena_ui_automation.py
======================

Unified, All-In-One Arena.ai Automation Engine.

Architecture:
  1. Opens Chrome directly with all 5 chat tabs in the foreground.
  2. Dynamically waits for each tab's DOM and message input to be ready.
  3. Pauses and brings tab to front if human CAPTCHA/Turnstile verification is needed.
  4. Bundles Git metadata + requested source files into the prompt.
  5. Concurrently submits prompts across all 5 models.
  6. Dynamically polls until all model streams finish.
  7. Overwrites standard persistent local deliverables:
     - responses/<model>_latest.md
     - responses/latest_arena_audit.md
     - arena_latest_copied_response.txt
"""

from __future__ import annotations

import argparse
import asyncio
import glob
import json
import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional
import urllib.request

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    async_playwright,
)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

DEFAULT_PORT = 19333
DEFAULT_CDP_URL = f"http://127.0.0.1:{DEFAULT_PORT}"
DEFAULT_USER_DATA = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data_Arena")
DEFAULT_CONFIG_FILE = "arena_chats_config.json"
DEFAULT_OUTPUT_DIR = "responses"
DEFAULT_STANDARDIZED_FILE = "arena_latest_copied_response.txt"

DEFAULT_CHATS = [
    {"model": "claude-sonnet-5", "url": "https://arena.ai/code/direct"},
    {"model": "gpt-5.3-codex", "url": "https://arena.ai/code/direct"},
    {"model": "deepseek-v4-pro-high", "url": "https://arena.ai/code/direct"},
    {"model": "grok-4.5", "url": "https://arena.ai/code/direct"},
    {"model": "gemini-3.1-pro-preview", "url": "https://arena.ai/code/direct"},
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
LOG = logging.getLogger("arena_automation")


# --------------------------------------------------------------------------- #
# Git Context Injection & Prompt Construction
# --------------------------------------------------------------------------- #

def get_git_context() -> dict[str, str]:
    """
    Extracts local Git metadata to inject into the AI prompt.
    This ensures the AI knows exactly which version of the code it is auditing.
    """
    # Define fallback defaults in case git commands fail (e.g., if not run inside a git repo)
    context = {
        "repo": "https://github.com/kbsingh1399/coinglass-trading.git",
        "branch": "arena/019fec7a-coinglass-trading",
        "commit": "f0e21a41141122a94d0d1a28fd57a328192de853",
        "subpath": "Engine_1_arena_PR",
    }
    try:
        # Dynamically fetch the git origin URL
        url = subprocess.check_output(["git", "config", "--get", "remote.origin.url"], text=True).strip()
        if url:
            context["repo"] = url
    except Exception:
        pass

    try:
        # Dynamically fetch the current active branch name
        branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], text=True).strip()
        if branch:
            context["branch"] = branch
    except Exception:
        pass

    try:
        # Dynamically fetch the exact HEAD commit SHA
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        if commit:
            context["commit"] = commit
    except Exception:
        pass

    return context


def format_prompt_with_git(raw_prompt: str, include_files: Optional[list[str]] = None) -> str:
    git_info = get_git_context()
    header = (
        f"=== REPOSITORY & LIVE CODEBASE CONTEXT ===\n"
        f"GitHub Repository: {git_info['repo']}\n"
        f"Branch: {git_info['branch']}\n"
        f"Commit SHA: {git_info['commit']}\n"
        f"Target Directory: {git_info['subpath']}/\n"
        f"===========================================\n\n"
        f"CRITICAL INSTRUCTION: Do NOT use UI file artifacts (e.g. Artifact cards). "
        f"If you need to provide code patches, write them DIRECTLY in the chat using standard Markdown code blocks.\n\n"
    )
    code_blocks = []
    if include_files:
        for fpath in include_files:
            if os.path.exists(fpath):
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                code_blocks.append(f"### SOURCE FILE: {os.path.basename(fpath)}\n```python\n{content}\n```\n")
    
    files_section = "\n".join(code_blocks) + "\n" if code_blocks else ""
    return header + files_section + raw_prompt.strip()


# --------------------------------------------------------------------------- #
# Dynamic Tab Loading, CAPTCHA Handling & Extraction
# --------------------------------------------------------------------------- #

async def check_and_handle_captcha(page: Page, model_name: str) -> None:
    """
    Detects if Cloudflare or a CAPTCHA challenge is blocking the page load.
    If detected, brings the tab to the foreground so the human operator can solve it manually.
    """
    # Loop up to 30 times (approx 60 seconds of waiting) to check for blockages
    for _ in range(30):
        try:
            # First, check if the chat input box (textarea) is visible. If it is, the page is clear.
            textarea_ready = await page.locator("textarea[name='message'], textarea.box-border, textarea:not([tabindex='-1'])").first.is_visible()
            if textarea_ready:
                return

            # Evaluate JavaScript inside the browser to look for known Cloudflare title/DOM signatures
            has_challenge = await page.evaluate("""() => {
                const title = document.title || '';
                const cfBlock = title.includes('Just a moment...') || title.includes('Attention Required!');
                const challengeStage = !!document.querySelector('#challenge-stage, #challenge-running, #cf-please-wait');
                return cfBlock || challengeStage;
            }""")
            
            # If no challenge is found but textarea isn't ready, just return and let the caller retry
            if not has_challenge:
                return
                
            # If challenge IS detected, log a warning and bring this specific tab to the user's screen
            LOG.warning(f"[{model_name}] [CAPTCHA DETECTED] Cloudflare challenge page active... Waiting for verification...")
            await page.bring_to_front()
            await asyncio.sleep(2.0) # Wait 2 seconds before checking again
        except Exception:
            return


async def wait_for_tab_ready(page: Page, model_name: str, target_url: str) -> None:
    LOG.info(f"[{model_name}] Navigating to {target_url} ...")
    await page.goto(target_url, wait_until="domcontentloaded", timeout=45000)

    try:
        # Wait a bit for the page to render
        await page.wait_for_timeout(1500)
        
        # Click "Max" if it exists
        try:
            max_btn = page.get_by_role("button", name="Max")
            if await max_btn.is_visible(timeout=2000):
                await max_btn.click()
        except Exception:
            pass

        # Search for model and select it
        search_input = page.get_by_placeholder("Search models")
        await search_input.click(timeout=5000)
        await search_input.fill(model_name)
        
        suggestion = page.get_by_label("Suggestions").get_by_text(model_name)
        await suggestion.click(timeout=5000)
        LOG.info(f"[{model_name}] Model selected from dropdown.")
    except Exception as e:
        LOG.error(f"[{model_name}] Error selecting model (may already be selected): {e}")

    textarea = page.locator("textarea[name='message'], textarea.box-border, textarea:not([tabindex='-1']), [aria-label='Describe the website or app'], [placeholder*='Describe']").first
    for attempt in range(25):
        if await textarea.is_visible():
            LOG.info(f"[{model_name}] Prompt input ready.")
            return
        await check_and_handle_captcha(page, model_name)
        await asyncio.sleep(1.0)

    raise TimeoutError(f"[{model_name}] Textarea did not become visible within 25 seconds.")


async def submit_prompt_in_tab(page: Page, prompt: str, model_name: str) -> None:
    """
    Inputs the generated codebase prompt into the chat UI and clicks send.
    It uses clipboard pasting because typing 20k+ chars key-by-key freezes React UIs.
    """
    LOG.info(f"[{model_name}] Entering prompt via keyboard dispatch (React-compatible)...")
    
    textarea = page.locator("textarea[name='message'], textarea.box-border, textarea:not([tabindex='-1']), [aria-label='Describe the website or app'], [placeholder*='Describe']").first
    await textarea.scroll_into_view_if_needed() # Ensure it's on screen
    await textarea.click() # Focus the input box
    await page.wait_for_timeout(200)

    # Highlight and delete any old text left over from a previous session
    await page.keyboard.press("Control+A")
    await page.keyboard.press("Delete")
    await page.wait_for_timeout(100)

    # Paste the giant prompt from the system clipboard (lightning fast compared to typing)
    await page.keyboard.press("Control+V")
    await page.wait_for_timeout(1000)

    # Iterate through a list of known "Send" button CSS selectors (Arena UI changes often)
    sent = False
    for selector in [
        "button[data-testid='send-button']",
        "button[aria-label='Send message']",
        "button[aria-label='Send']",
        "form button[type='submit']",
        "button:has(svg[data-testid*='send' i])",
    ]:
        try:
            btn = page.locator(selector).first
            # If this specific selector exists, is visible, and isn't grayed out
            if await btn.count() > 0 and await btn.is_visible() and await btn.is_enabled():
                await btn.click() # Click it!
                sent = True
                LOG.info(f"[{model_name}] Clicked send via selector: {selector}")
                break
        except Exception:
            continue

    if not sent:
        # Fallback 1: If CSS selectors fail, inject Javascript to find any button labeled "send"
        clicked = await page.evaluate("""
            () => {
                const btns = Array.from(document.querySelectorAll('button'));
                const send = btns.find(b => {
                    const label = (b.getAttribute('aria-label') || b.textContent || '').toLowerCase();
                    return !b.disabled && (label.includes('send') || b.type === 'submit');
                });
                if (send) { send.click(); return true; }
                return false;
            }
        """)
        if clicked:
            LOG.info(f"[{model_name}] Clicked send via JS fallback.")
        else:
            # Fallback 2: Literally just press the Enter key on the keyboard
            await page.keyboard.press("Enter")
            LOG.info(f"[{model_name}] Pressed Enter as last resort.")

    LOG.info(f"[{model_name}] Prompt submitted. Waiting for stream...")


async def wait_and_extract_response(page: Page, model_name: str, prompt: str, timeout_seconds: int = 240) -> str:
    """
    Polls the page continuously to watch the AI generate its response.
    It stops when the "Like this response" button appears, indicating completion.
    """
    LOG.info(f"[{model_name}] Monitoring output stream for 'Like this response' button...")
    
    try:
        # Wait up to timeout_seconds for the Like button to appear
        like_btn = page.get_by_role("button", name="Like this response", exact=True).first
        await like_btn.wait_for(state="visible", timeout=timeout_seconds * 1000)
        LOG.info(f"[{model_name}] 'Like this response' button detected. Stream completed.")
        
        # Click the Like button as requested
        await like_btn.click(timeout=5000)
        LOG.info(f"[{model_name}] Clicked 'Like this response' button.")
        
        # Give UI a moment to settle
        await page.wait_for_timeout(500)
        
        # Use JS to scrape the latest AI response
        raw = await page.evaluate("""(promptText) => {
            const headers = Array.from(document.querySelectorAll('div, span, h2, h3, h4, p'))
                .filter(el => {
                    const txt = el.innerText.trim().toLowerCase();
                    return (txt.includes('claude-') || txt.includes('gpt-') || txt.includes('deepseek-') || 
                            txt.includes('grok-') || txt.includes('gemini-')) && txt.length < 50;
                });
            
            let extractedText = '';
            if (headers.length > 0) {
                const lastHeader = headers[headers.length - 1];
                
                let container = lastHeader.parentElement;
                for (let i = 0; i < 4; i++) {
                    if (!container.parentElement) break;
                    if (container.innerText.length > 100 && container.children.length > 1) {
                        break; 
                    }
                    container = container.parentElement;
                }
                if (container) {
                    extractedText = container.innerText;
                }
            }

            if (!extractedText || extractedText.length < 20) {
                const candidates = Array.from(document.querySelectorAll('div, section, article'))
                    .filter(el => {
                        const rect = el.getBoundingClientRect();
                        return rect.x >= 230 && rect.width > 200 && rect.height > 20;
                    })
                    .map(el => el.innerText.trim())
                    .filter(t => t.length > 20 && !t.includes('singhkaranbir0248@gmail.com') && !t.includes('Terms of Use'));
                candidates.sort((a, b) => b.length - a.length);
                extractedText = candidates[0] || '';
            }
            
            return extractedText;
        }""", prompt)

        lines = raw.splitlines() if raw else []
        cleaned = []
        for line in lines:
            l = line.strip()
            if not l or l in ["Direct", "Max", "Code", "Add files", "Download", "No preview available", "Show More", "Show Less"]:
                continue
            if "Inputs are processed by third-party AI" in l or l.startswith("claude-") or l.startswith("gpt-") or l.startswith("gemini-"):
                continue
            cleaned.append(line)

        return "\n".join(cleaned).strip()

    except Exception as e:
        LOG.warning(f"[{model_name}] Stream extraction failed: {e}")
        return ""


async def process_single_model_tab(
    page: Page,
    model_name: str,
    target_url: str,
    prompt: str,
    output_dir: str,
    delay_before_start: int = 0,
) -> dict[str, Any]:
    try:
        if delay_before_start > 0:
            LOG.info(f"[{model_name}] Waiting {delay_before_start} seconds before starting to respect 1-minute interval...")
            await asyncio.sleep(delay_before_start)

        await wait_for_tab_ready(page, model_name, target_url)
        await submit_prompt_in_tab(page, prompt, model_name)
        content = await wait_and_extract_response(page, model_name, prompt)

        os.makedirs(output_dir, exist_ok=True)
        slug = re.sub(r"[^\w\-.]+", "_", model_name.strip()).strip("_")
        latestpath = os.path.join(output_dir, f"{slug}_latest.md")

        doc = (
            f"# Model Codebase Audit: {model_name}\n\n"
            f"**Timestamp:** {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"**Chat URL:** {target_url}\n\n"
            f"## Audit Review & Recommendations\n\n{content}\n"
        )
        with open(latestpath, "w", encoding="utf-8") as f:
            f.write(doc)

        LOG.info(f"[{model_name}] [SUCCESS] Written to standard file: {latestpath}")
        return {"model": model_name, "status": "success", "content": content, "file": latestpath, "url": target_url}

    except Exception as e:
        LOG.error(f"[{model_name}] [FAILED] {e}")
        return {"model": model_name, "status": "failed", "error": str(e), "url": target_url}


# --------------------------------------------------------------------------- #
# Runner Orchestration
# --------------------------------------------------------------------------- #

def ensure_chrome_running(port: int, user_data_dir: str):
    import socket
    
    # Check if port is open
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        is_open = s.connect_ex(('127.0.0.1', port)) == 0
        
    if is_open:
        LOG.info(f"Chrome is already listening on port {port}.")
        return
        
    LOG.info(f"Chrome is not running on port {port}. Attempting to launch...")
    
    # Find chrome.exe
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")
    ]
    chrome_exe = None
    for path in chrome_paths:
        if os.path.exists(path):
            chrome_exe = path
            break
            
    if not chrome_exe:
        raise FileNotFoundError("Could not find chrome.exe in standard locations.")
        
    os.makedirs(user_data_dir, exist_ok=True)
    
    # Launch Chrome
    cmd = [
        chrome_exe,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check"
    ]
    
    # We use Popen so we don't block
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Wait for the port to open
    for _ in range(15):
        time.sleep(1)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', port)) == 0:
                LOG.info(f"Chrome successfully launched and listening on port {port}.")
                return
                
    raise RuntimeError(f"Launched Chrome but it did not bind to port {port} within 15 seconds.")


async def run_evaluation(
    prompt: str,
    chats: list[dict[str, str]],
    cdp_url: str = DEFAULT_CDP_URL,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    include_files: Optional[list[str]] = None,
) -> None:
    # Auto-launch Chrome if needed before we even try to connect
    port = int(cdp_url.split(":")[-1]) if ":" in cdp_url else DEFAULT_PORT
    ensure_chrome_running(port, DEFAULT_USER_DATA)

    formatted_prompt = format_prompt_with_git(prompt, include_files=include_files)
    import pyperclip
    pyperclip.copy(formatted_prompt)

    LOG.info(f"Connecting to Chrome CDP on {cdp_url} ...")
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(cdp_url)
        context = browser.contexts[0]

        start_time = time.time()
        LOG.info(f"=== PROCESSING ALL {len(chats)} TABS CONCURRENTLY ===")

        # Map existing pages or create new pages for missing chats
        existing_pages = context.pages
        model_pages: list[tuple[str, str, Page]] = []

        for i, chat in enumerate(chats):
            target_url = chat["url"]
            model_name = chat["model"]
            
            if i < len(existing_pages):
                matched_page = existing_pages[i]
            else:
                matched_page = await context.new_page()

            model_pages.append((model_name, target_url, matched_page))

        coros = [
            process_single_model_tab(
                page=mp[2],
                model_name=mp[0],
                target_url=mp[1],
                prompt=formatted_prompt,
                output_dir=output_dir,
                delay_before_start=i * 60,
            )
            for i, mp in enumerate(model_pages)
        ]
        results = await asyncio.gather(*coros)

        # Write unified standard consensus audit deliverable
        consolidated_path = os.path.join(output_dir, "latest_arena_audit.md")
        root_standard_path = DEFAULT_STANDARDIZED_FILE

        consolidated_doc = [
            f"# Multi-Model Quantitative Audit Consensus Report",
            f"**Generated:** {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Git Commit:** {get_git_context()['commit']}",
            f"**Branch:** {get_git_context()['branch']}\n",
            "## Summary of Model Findings\n",
        ]
        for r in results:
            m_name = r["model"]
            status = r["status"].upper()
            body = r.get("content", r.get("error", "No content extracted"))
            consolidated_doc.append(f"### Model: {m_name} [{status}]\n\n{body}\n\n---\n")

        full_text = "\n".join(consolidated_doc)
        with open(consolidated_path, "w", encoding="utf-8") as f:
            f.write(full_text)
        with open(root_standard_path, "w", encoding="utf-8") as f:
            f.write(full_text)

        elapsed = time.time() - start_time
        print("\n" + "=" * 70)
        print(f"ARENA.AI EVALUATION SUMMARY (Total Elapsed: {elapsed:.1f}s)")
        print("=" * 70)
        for r in results:
            sym = "[OK]" if r["status"] == "success" else "[FAILED]"
            target = r.get("file") or r.get("error")
            print(f"  {sym} {r['model']}:\n       -> {target}")
        print("-" * 70)
        print(f"Standard Overwritten Output: {root_standard_path}")
        print("=" * 70 + "\n")

        LOG.info("Closing browser tabs and cleaning up...")
        await browser.close()
        
        # Explicitly kill the Chrome instance we attached to on port 19333
        LOG.info("Shutting down Chrome process on port 19333...")
        try:
            output = subprocess.check_output("netstat -ano | findstr :19333", shell=True, text=True)
            for line in output.splitlines():
                if ":19333" in line and "LISTENING" in line:
                    parts = line.strip().split()
                    if len(parts) >= 5:
                        pid = parts[-1]
                        subprocess.run(f"taskkill /F /PID {pid} /T", shell=True, capture_output=True)
        except Exception:
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Unified Arena.ai Multi-Model Automation Engine")
    parser.add_argument("--prompt", type=str, default="arena_prompt.txt", help="Prompt text or path to prompt file")
    parser.add_argument("--files", nargs="*", help="Source files to bundle directly into prompt")
    parser.add_argument("--config", type=str, default=DEFAULT_CONFIG_FILE, help="Path to chat configuration JSON file")
    parser.add_argument("--cdp-url", type=str, default=DEFAULT_CDP_URL, help="Chrome CDP URL")
    parser.add_argument("--output-dir", type=str, default=DEFAULT_OUTPUT_DIR, help="Deliverables output directory")

    args = parser.parse_args()

    chats = DEFAULT_CHATS
    if args.config and os.path.exists(args.config):
        with open(args.config, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            chats = cfg.get("chats", DEFAULT_CHATS)

    # Force all URLs to use the direct code chat interface
    for chat in chats:
        chat["url"] = "https://arena.ai/code/direct"

    prompt_text = args.prompt
    if os.path.isfile(prompt_text):
        with open(prompt_text, "r", encoding="utf-8", errors="replace") as f:
            prompt_text = f.read()

    asyncio.run(
        run_evaluation(
            prompt=prompt_text,
            chats=chats,
            cdp_url=args.cdp_url,
            output_dir=args.output_dir,
            include_files=args.files,
        )
    )


if __name__ == "__main__":
    main()
