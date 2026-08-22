import asyncio
from playwright.async_api import async_playwright

async def check_claude_tabs():
    async with async_playwright() as p:
        try:
            print("Connecting to Chrome on port 19333...")
            browser = await p.chromium.connect_over_cdp("http://localhost:19333")
            contexts = browser.contexts
            if not contexts:
                print("No contexts found.")
                return

            context = contexts[0]
            pages = context.pages
            print(f"Found {len(pages)} open pages.")

            for i, page in enumerate(pages):
                title = await page.title()
                url = page.url
                print(f"Tab {i}: Title: '{title}', URL: '{url}'")
                
                if "claude.ai" in url:
                    # Let's see what's on the page
                    print(f"  -> Claude page found. Checking state...")
                    # Get some text or input fields
                    content = await page.content()
                    inputs = await page.evaluate('''() => {
                        return Array.from(document.querySelectorAll('input')).map(i => ({
                            type: i.type,
                            value: i.value,
                            name: i.name
                        }));
                    }''')
                    print(f"  -> Input fields found: {inputs}")

            await browser.close()
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(check_claude_tabs())
