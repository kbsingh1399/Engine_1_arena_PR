import asyncio
from playwright.async_api import async_playwright
import os

async def main():
    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp("http://localhost:19333")
            context = browser.contexts[0]
            pages = context.pages
            print(f"Connected. Found {len(pages)} pages.")
            
            # Find the arena.ai page
            arena_page = None
            for page in pages:
                if "arena.ai" in page.url:
                    arena_page = page
                    break
            
            if not arena_page:
                print("arena.ai page not found.")
                return

            print(f"Found arena page: {arena_page.url}")
            
            # Let's dump some basic HTML to understand the structure
            html = await arena_page.evaluate("document.body.innerHTML")
            
            os.makedirs("scratch", exist_ok=True)
            with open("scratch/arena_dom.html", "w", encoding="utf-8") as f:
                f.write(html)
            print("Saved DOM to scratch/arena_dom.html")
            
        except Exception as e:
            print(f"Error: {e}")

asyncio.run(main())
