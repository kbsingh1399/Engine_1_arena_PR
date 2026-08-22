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
            
            # The input field
            input_locator = page.get_by_placeholder("Type your coupon code here")
            if await input_locator.count() == 0:
                print("Could not find the coupon input box.")
                return
                
            for coupon in coupons:
                print(f"--- Trying coupon: {coupon} ---")
                
                await input_locator.fill(coupon)
                
                apply_btn = page.locator("text=Apply").first
                await apply_btn.click()
                
                await asyncio.sleep(2) # Wait for network request to validate
                
                # Check all text on the page for error indicators
                page_text = await page.evaluate("document.body.innerText")
                lower_text = page_text.lower()
                
                if "invalid" in lower_text or "not applicable" in lower_text or "expired" in lower_text or "does not exist" in lower_text or "error" in lower_text:
                    print(f"Coupon {coupon} failed (found error keyword).")
                else:
                    # Let's see if there's a success message, e.g. "discount" or "applied"
                    print(f"Coupon {coupon} MIGHT have succeeded!")
                    print("Page text snippet:", page_text[:200])
                    break # Stop at the first potentially successful coupon
                
                # Clear for next
                await input_locator.fill("")
                await asyncio.sleep(1)
                
        except Exception as e:
            print(f"Exception: {e}")

asyncio.run(run())
