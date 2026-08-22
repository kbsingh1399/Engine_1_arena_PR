import asyncio
import time
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        try:
            print("Connecting to Chrome on port 19333...")
            browser = await p.chromium.connect_over_cdp("http://localhost:19333")
            contexts = browser.contexts
            if not contexts:
                print("No contexts found.")
                return
            
            page = contexts[0].pages[0]
            print(f"Connected to page: {await page.title()}")
            
            coupons = ["TAKE100", "GET100", "BMS150", "BMS125", "BINGO", "MOVIE100", "PAYTM100", "AMAZON100", "WELCOME75"]
            
            for coupon in coupons:
                print(f"Trying coupon: {coupon}")
                # Wait for the input box
                # The placeholder is "Type your coupon code here"
                input_locator = page.get_by_placeholder("Type your coupon code here")
                if await input_locator.count() == 0:
                    print("Could not find the coupon input box.")
                    break
                    
                await input_locator.fill(coupon)
                
                # Click Apply. The apply button might be a button or div next to it.
                # Let's find the text "Apply" inside the offer box.
                # In the screenshot, there is an "Apply" text in pink next to the input.
                apply_btn = page.locator("text=Apply").first
                await apply_btn.click()
                
                await asyncio.sleep(2) # wait for validation
                
                # check if there's an error message or success message
                # If there's an error, it might say "Invalid code" or similar
                # Let's get all text on the page to see if it succeeded or failed, or just print a success status.
                # Usually the input gets cleared or an error shows up.
                
                # To be safe, we will just print what happened and move to the next by clearing the input if it's still there.
                print(f"Tested {coupon}. Check the browser for result.")
                
                await asyncio.sleep(1)
                await input_locator.fill("") # clear for next
                
        except Exception as e:
            print(f"Error: {e}")

asyncio.run(run())
