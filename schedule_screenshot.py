import os
import sys
import json
import asyncio
import websockets
from datetime import datetime

async def capture_chrome_cdp():
    uri = "ws://localhost:19233/devtools/page/03C5A7BF0C80C4C2724716C441077F16"
    workspace_dir = r"c:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR"
    screenshot_path = os.path.join(workspace_dir, "screenshot_1.png")
    
    if os.path.exists(screenshot_path):
        try:
            os.remove(screenshot_path)
        except:
            pass

    try:
        async with websockets.connect(uri) as ws:
            print("Connected to Chrome CDP.")
            # Request screenshot
            await ws.send(json.dumps({
                "id": 1,
                "method": "Page.captureScreenshot",
                "params": {"format": "png", "quality": 100}
            }))
            
            res_str = await ws.recv()
            res = json.loads(res_str)
            
            if 'result' in res and 'data' in res['result']:
                import base64
                img_data = base64.b64decode(res['result']['data'])
                with open(screenshot_path, "wb") as f:
                    f.write(img_data)
                print(f"[SUCCESS] Screenshot saved to {screenshot_path}")
            else:
                print(f"[ERROR] Screenshot failed: {res}")
    except Exception as e:
        print(f"[ERROR] CDP Connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(capture_chrome_cdp())
