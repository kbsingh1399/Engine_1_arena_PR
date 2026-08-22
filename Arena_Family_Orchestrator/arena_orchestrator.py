import asyncio
from playwright.async_api import async_playwright

# Configuration
MODELS = ["gemini-3-flash", "qwen3.5-397b-a17b", "claude-sonnet-4-6"]
PROMPT = "Write a python script that connects to chrome over cdp and prints the title of all pages."
CDP_URL = "http://localhost:19333"

async def setup_tab(context, model_name):
    print(f"[{model_name}] Setting up tab...")
    page = await context.new_page()
    await page.goto("https://arena.ai/code/direct")
    await page.wait_for_load_state("networkidle")
    
    # Give it a second to render
    await asyncio.sleep(2)
    
    print(f"[{model_name}] Selecting model...")
    # Click the current model button to open the dropdown. 
    # Usually the dropdown button is next to the mode selector (e.g. "Max")
    # We try to click the button that is likely the model selector.
    # From our DOM exploration, the model button is around index 29 or has text of the current model.
    # A robust way is to click the second button in the header, or just find the one with aria-haspopup.
    try:
        # Trying to find the header dropdown button
        # In the DOM we saw "Direct" then "Max" (or whatever model is selected).
        # We'll click the button containing "Max" or similar. If we don't know the default, we can click the button next to "Direct".
        await page.locator('button', has_text="Direct").locator('..').locator('button').nth(1).click(timeout=3000)
    except:
        # Fallback: Just click the second to last button that has text (hacky but works if DOM is stable)
        buttons = await page.locator('button').all()
        for b in reversed(buttons):
            text = await b.inner_text()
            if text and text.strip() not in ["Direct", "Add files", "Code", "Text", "Image", "Search"]:
                await b.click()
                break

    await asyncio.sleep(1)
    
    # Click the model in the dropdown
    print(f"[{model_name}] Clicking model in dropdown...")
    try:
        # Find the element containing the exact model name and click it
        await page.locator(f'text="{model_name}"').first.click(timeout=3000)
    except Exception as e:
        print(f"[{model_name}] Could not find model in dropdown: {e}. It might already be selected.")
        # Press escape to close dropdown if it failed
        await page.keyboard.press("Escape")
        
    return page

async def prompt_model(page, model_name, prompt):
    print(f"[{model_name}] Sending prompt...")
    # Type in the textarea
    textarea = page.locator('textarea[name="message"]')
    await textarea.fill(prompt)
    await asyncio.sleep(1)
    
    # Press Enter (without shift) to send, or find the submit button.
    # The submit button is typically the next sibling or near the textarea.
    await textarea.press("Enter")
    
    print(f"[{model_name}] Waiting for response to finish...")
    # Wait for the response. Usually there is a stop button that turns back into a send button, 
    # or a typing indicator disappears.
    # We'll poll for 30 seconds, checking if the response is stable.
    # For now, let's just wait a fixed amount of time for the demo.
    await asyncio.sleep(15)
    
    # Extract the response. Usually it's in a markdown div or similar.
    # We can try to grab the last message in the chat.
    # Chat bubbles often have specific classes or are just the last text content.
    print(f"[{model_name}] Extracting response...")
    # This selector might need tuning based on actual arena.ai DOM
    try:
        # Get all text in the main chat area
        # We can extract the innerText of the body and try to parse, but better to just get all paragraphs
        # in the main scrollable area.
        all_text = await page.evaluate("document.body.innerText")
        # Just saving it to a file for now since it might be large
        filename = f"scratch/response_{model_name}.txt"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(all_text)
        print(f"[{model_name}] Response saved to {filename}")
    except Exception as e:
        print(f"[{model_name}] Failed to extract response: {e}")

async def main():
    print("Connecting to Chrome CDP...")
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP_URL)
        context = browser.contexts[0]
        
        # Phase 1: Setup all tabs in parallel
        print("Setting up tabs...")
        pages = await asyncio.gather(*(setup_tab(context, model) for model in MODELS))
        
        # Phase 2: Send prompts in parallel
        print("Sending prompts to all models...")
        await asyncio.gather(*(prompt_model(page, model, PROMPT) for page, model in zip(pages, MODELS)))
        
        print("Done! Check the scratch/ folder for responses.")

if __name__ == "__main__":
    asyncio.run(main())
