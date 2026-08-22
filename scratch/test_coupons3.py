import asyncio
import time
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp("http://localhost:19333")
            contexts = browser.contexts
            if not contexts: return
            
            page = contexts[0].pages[0]
            
            coupons = ["BMS150", "BMS125", "BINGO", "MOVIE100", "PAYTM100", "AMAZON100", "WELCOME75", "BMS50", "WIN100", "CB100", "FLAT150", "BMSNEW", "BMS200", "NEWUSER"]
            
            input_locator = page.get_by_placeholder("Type your coupon code here")
            if await input_locator.count() == 0: return
                
            for coupon in coupons:
                print(f"--- Trying coupon: {coupon} ---")
                
                await input_locator.fill(coupon)
                
                apply_btn = page.locator("text=Apply").first
                await apply_btn.click()
                
                await asyncio.sleep(2) # Wait for network request to validate
                
                page_text = await page.evaluate("document.body.innerText")
                lower_text = page_text.lower()
                
                if "invalid" in lower_text or "not applicable" in lower_text or "expired" in lower_text or "does not exist" in lower_text or "error" in lower_text or "enter a valid promo" in lower_text:
                    print(f"Coupon {coupon} failed.")
                else:
                    print(f"Coupon {coupon} MIGHT have succeeded!")
                    print("Page text snippet:", page_text[:200])
                    break
                
                await input_locator.fill("")
                await asyncio.sleep(1)
                
        except Exception as e:
            print(f"Exception: {e}")

asyncio.run(run())
