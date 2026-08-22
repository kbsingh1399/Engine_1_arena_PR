from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import asyncio
from playwright.async_api import async_playwright

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

class PromptRequest(BaseModel):
    models: list[str]
    prompt: str

CDP_URL = "http://localhost:19333"
browser = None
context = None
playwright_instance = None
model_pages = {}  # model_name -> page

# We use a lock to prevent concurrent tab interaction which causes CAPTCHAs
interaction_lock = asyncio.Lock()

@app.on_event("startup")
async def startup_event():
    global browser, context, playwright_instance
    print("Starting Playwright CDP connection...")
    playwright_instance = await async_playwright().start()
    browser = await playwright_instance.chromium.connect_over_cdp(CDP_URL)
    context = browser.contexts[0]
    print("Connected to Chrome CDP.")

@app.on_event("shutdown")
async def shutdown_event():
    print("Disconnecting CDP...")
    # Do not close the browser context, as it's the user's browser
    if browser:
        await browser.close()
    if playwright_instance:
        await playwright_instance.stop()

@app.get("/")
async def root():
    return FileResponse("static/index.html")

async def get_or_create_page(model_name: str):
    if model_name in model_pages and not model_pages[model_name].is_closed():
        return model_pages[model_name]
        
    print(f"[{model_name}] Creating new tab...")
    page = await context.new_page()
    await page.goto("https://arena.ai/code/direct")
    await page.wait_for_load_state("networkidle")
    await asyncio.sleep(2)
    
    print(f"[{model_name}] Selecting model...")
    try:
        await page.locator('button', has_text="Direct").locator('..').locator('button').nth(1).click(timeout=3000)
    except:
        buttons = await page.locator('button').all()
        for b in reversed(buttons):
            text = await b.inner_text()
            if text and text.strip() not in ["Direct", "Add files", "Code", "Text", "Image", "Search"]:
                await b.click()
                break

    await asyncio.sleep(1)
    try:
        await page.locator(f'text="{model_name}"').first.click(timeout=3000)
    except Exception as e:
        print(f"[{model_name}] Model not found in dropdown (might be selected already).")
        await page.keyboard.press("Escape")
        
    model_pages[model_name] = page
    return page

async def process_prompt(model_name: str, prompt: str):
    async with interaction_lock:
        page = await get_or_create_page(model_name)
        print(f"[{model_name}] Sending prompt...")
        
        textarea = page.locator('textarea[name="message"]')
        await textarea.fill(prompt)
        await asyncio.sleep(0.5)
        await textarea.press("Enter")
        
        # We need a robust way to know when generation is done.
        # For simplicity in this demo backend, we wait a fixed time.
        # A true production script would poll the DOM for the stop button disappearing.
        print(f"[{model_name}] Waiting 15s for generation...")
        await asyncio.sleep(15)
        
        try:
            all_text = await page.evaluate("document.body.innerText")
            # Extract everything after the prompt as a heuristic, or just return all text.
            # Usually the last large block of text is the response.
            # We will return the raw text, and the UI can render it.
            # Let's try to get just the last message.
            # Often chat bubbles are in divs. We can extract the innerText of the last message element.
            # We'll just return all_text for robustness right now.
            
            return {"model": model_name, "response": all_text}
        except Exception as e:
            return {"model": model_name, "response": f"Error extracting response: {e}"}

@app.post("/api/prompt")
async def api_prompt(req: PromptRequest):
    results = []
    # Process sequentially to avoid CAPTCHAs
    for model in req.models:
        res = await process_prompt(model, req.prompt)
        results.append(res)
    return {"results": results}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
