import asyncio
from playwright.async_api import async_playwright

async def extract_arena():
    try:
        print("Connecting to CDP...")
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp("http://127.0.0.1:19333")
            context = browser.contexts[0]
            
            arena_page = None
            for page in context.pages:
                if "arena.ai" in page.url:
                    arena_page = page
                    break
            
            if not arena_page:
                print("Could not find arena.ai tab.")
                return
            
            print(f"Found arena tab: {arena_page.url}")
            
            # Wait a bit just in case the models are still streaming
            await asyncio.sleep(2)
            
            content = await arena_page.content()
            
            # Save the full HTML for parsing
            with open("C:\\Users\\SIGMA\\Documents\\Project - Coinglass Trading\\Engine_1_arena_PR\\scratch\\arena_dom.html", "w", encoding="utf-8") as f:
                f.write(content)
            
            # Extract text
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(content, 'html.parser')
            text = soup.get_text(separator='\n', strip=True)
            with open("C:\\Users\\SIGMA\\Documents\\Project - Coinglass Trading\\Engine_1_arena_PR\\scratch\\arena_text.txt", "w", encoding="utf-8") as f:
                f.write(text)
            
            print("Successfully extracted DOM and Text.")
            await browser.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(extract_arena())
