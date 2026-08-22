import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:19333")
        context = browser.contexts[0]
        page = None
        for p in context.pages:
            if "arena.ai" in p.url:
                page = p
                break
        
        if not page:
            print("No arena page found")
            return
            
        print("Page URL:", page.url)
        # Find all buttons
        buttons = await page.locator("button").all()
        for i, b in enumerate(buttons):
            text = await b.inner_text()
            print(f"Button {i}: {text.strip() if text else '<no text>'}")

asyncio.run(main())
