from playwright.sync_api import sync_playwright
import json

def extract_tv_data():
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://localhost:19233")
        contexts = browser.contexts
        if not contexts:
            print("No browser contexts found.")
            return

        page = contexts[0].pages[0]
        print(f"Connected to page: {page.url}")
        
        page.screenshot(path="screenshot_pw.png")
        print("Saved screenshot to screenshot_pw.png")

        # TradingView is often in an iframe, let's dump texts from all frames
        for idx, frame in enumerate(page.frames):
            print(f"Frame {idx}: {frame.name} - {frame.url}")
            try:
                # Execute a script inside the frame to get all inner text of elements that might be the legend
                text = frame.evaluate("""() => {
                    return document.body.innerText;
                }""")
                with open(f"frame_{idx}_text.txt", "w", encoding="utf-8") as f:
                    f.write(text)
                print(f"Dumped text for frame {idx}")
            except Exception as e:
                print(f"Failed to dump text for frame {idx}: {e}")
                    
        browser.close()

if __name__ == "__main__":
    extract_tv_data()
