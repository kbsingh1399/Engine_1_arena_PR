import asyncio
import os
from playwright.async_api import async_playwright

async def main():
    print("Connecting to existing Chrome instance on port 19333...")
    
    async with async_playwright() as p: 
        try:
            # Connect to the running Chrome instance (must be started via preflight.py or manually with remote-debugging-port)
            browser = await p.chromium.connect_over_cdp("http://127.0.0.1:19333")
            context = browser.contexts[0]
            
            # Create a new tab and navigate to the target URL
            page = await context.new_page()
            await page.set_viewport_size({"width": 1920, "height": 1080})
            
            print("Navigating to https://arena.ai/code/direct ...")
            await page.goto("https://arena.ai/code/direct")
            
            print("\n" + "="*60)
            print("PLAYWRIGHT INSPECTOR OPENED")
            print("="*60)
            print("1. Click the 'Record' button in the Playwright Inspector window.")
            print("2. Perform your actions (Start New Chat, Select Model, etc) in the browser.")
            print("3. Copy the generated code from the Inspector and share it here.")
            print("4. Close the Inspector window or hit 'Resume' when finished.")
            print("="*60 + "\n")
            
            # This triggers the Playwright Inspector (codegen UI) to pop up
            await page.pause()
            
        except Exception as e:
            print(f"\n[ERROR] Failed to connect: {e}")
            print("\nMake sure your persistent Chrome instance is running on port 19333.")
            print("You can start it using your existing preflight script or by running:")
            print(r'start chrome.exe --remote-debugging-port=19333 --user-data-dir="%LOCALAPPDATA%\Google\Chrome\User Data_Arena"')

if __name__ == "__main__":
    asyncio.run(main())
