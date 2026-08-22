import asyncio
import sys
import json
import uuid
import aiohttp


def make_uuid7():
    return str(uuid.uuid7())

sys.stdout.reconfigure(line_buffering=True)

RECAPTCHA_JS = """
async () => {
    try {
        const t = await window.grecaptcha.enterprise.execute(
            '6LeTGMcsAAAAALuIlkVwIxaAuZA8VledA6d3Nnb0', {action: 'submit'}
        );
        return t;
    } catch(e) {
        return 'ERROR:' + e.toString();
    }
}
"""


async def find_best_arena_page(ctx):
    """Find an Arena page that has a working reCaptcha context."""
    for pg in ctx.pages:
        if "arena.ai" not in pg.url:
            continue
        result = await pg.evaluate(RECAPTCHA_JS)
        if not str(result).startswith("ERROR"):
            return pg, result
    return None, None


async def main():
    from playwright.async_api import async_playwright

    print("Connecting to browser via CDP...")
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        ctx = browser.contexts[0]
        print(f"Pages open: {len(ctx.pages)}")

        page, token = await find_best_arena_page(ctx)

        if page is None:
            print("No arena.ai page has reCaptcha. Navigating...")
            page = ctx.pages[0]
            await page.goto("https://arena.ai/code/direct", wait_until="networkidle")
            await asyncio.sleep(4)
            token = await page.evaluate(RECAPTCHA_JS)

        if str(token).startswith("ERROR"):
            print(f"reCaptcha unavailable: {token}")
            return

        print(f"Using page: {page.url[:70]}")
        print(f"reCaptcha token: {len(token)} chars OK")

        # Extract cookies
        all_cookies = await ctx.cookies()
        cookies = {c["name"]: c["value"] for c in all_cookies if "arena.ai" in c.get("domain", "")}
        print(f"Cookies: {len(cookies)}")

        # Test with one model: glm-5.3 (max), top webdev rank=8
        model_id = "01a00134-44ac-7f9c-b4a7-b720acebaa97"
        payload = {
            "id": make_uuid7(),
            "mode": "direct-battle",
            "modelAId": model_id,
            "userMessageId": make_uuid7(),
            "modelAMessageId": make_uuid7(),
            "userMessage": {
                "content": "Say hello in exactly 5 words.",
                "experimental_attachments": [],
                "metadata": {}
            },
            "modality": "webdev",
            "recaptchaV3Token": token
        }
        cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
        headers = {
            "content-type": "text/plain;charset=UTF-8",
            "origin": "https://arena.ai",
            "referer": "https://arena.ai/code/direct",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "cookie": cookie_str
        }

        print("\nCalling Arena API directly (no UI)...")
        connector = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.post(
                "https://arena.ai/nextjs-api/stream/create-evaluation",
                data=json.dumps(payload),
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=90)
            ) as resp:
                print(f"HTTP {resp.status}")
                raw = await resp.text()
                print(f"Raw response ({len(raw)} chars):\n{raw[:500]}")


asyncio.run(main())
