import asyncio
import json
from playwright.async_api import async_playwright

async def extract_left_right():
    async with async_playwright() as p:
        try:
            print("Connecting to Chrome on port 19333...")
            browser = await p.chromium.connect_over_cdp("http://localhost:19333")
            
            arena_page = None
            for context in browser.contexts:
                for page in context.pages:
                    if "arena.ai" in page.url or "lmsys" in page.url:
                        arena_page = page
                        break
            
            if not arena_page:
                print("❌ Could not find an active Arena.ai tab.")
                return

            title = await arena_page.title()
            print(f"Connected to tab: {title}")
            
            # Use Javascript to get all .prose elements and their client bounding rects
            data = await arena_page.evaluate('''() => {
                const proseElements = Array.from(document.querySelectorAll('.prose.text-wrap'));
                if (proseElements.length === 0) return {error: "No prose elements found"};
                
                const screenWidth = window.innerWidth;
                const halfScreen = screenWidth / 2;
                
                let leftLast = null;
                let rightLast = null;
                
                // Find the last element in the left half and right half
                for (let i = proseElements.length - 1; i >= 0; i--) {
                    const rect = proseElements[i].getBoundingClientRect();
                    const center = rect.left + rect.width / 2;
                    
                    if (center < halfScreen && leftLast === null) {
                        leftLast = proseElements[i].innerText;
                    } else if (center >= halfScreen && rightLast === null) {
                        rightLast = proseElements[i].innerText;
                    }
                    
                    if (leftLast !== null && rightLast !== null) break;
                }
                
                return {
                    left: leftLast || "No response found",
                    right: rightLast || "No response found"
                };
            }''')
            
            if "error" in data:
                print(f"❌ Extractor Error: {data['error']}")
                return
                
            left_text = data['left']
            right_text = data['right']
            
            print(f"\n--- LEFT MODEL (Length: {len(left_text)}) ---")
            print(left_text[:500] + ("..." if len(left_text) > 500 else ""))
            
            print(f"\n--- RIGHT MODEL (Length: {len(right_text)}) ---")
            print(right_text[:500] + ("..." if len(right_text) > 500 else ""))
            
            with open("arena_layer_output.txt", "w", encoding="utf-8") as f:
                f.write("=== LEFT MODEL ===\n")
                f.write(left_text)
                f.write("\n\n=== RIGHT MODEL ===\n")
                f.write(right_text)
                
        except Exception as e:
            print(f"Connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(extract_left_right())
