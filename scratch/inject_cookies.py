"""
inject_cookies.py
Reads arena.ai cookies from the real Chrome profile (DPAPI decrypted)
and injects them into the running CDP debug Chrome session.
"""
import sqlite3
import shutil
import os
import json
import asyncio
import base64
import tempfile

# ---------------------------------------------------------------------------
# Step 1: Read + decrypt cookies from the real Chrome profile
# ---------------------------------------------------------------------------

def get_encryption_key():
    """Read the AES key from Chrome's Local State (DPAPI protected on Windows)."""
    import ctypes
    import struct

    local_state_path = os.path.expandvars(
        r"%LOCALAPPDATA%\Google\Chrome\User Data\Local State"
    )
    with open(local_state_path, "r", encoding="utf-8") as f:
        local_state = json.load(f)

    encrypted_key_b64 = local_state["os_crypt"]["encrypted_key"]
    encrypted_key = base64.b64decode(encrypted_key_b64)
    # Strip the DPAPI prefix "DPAPI"
    encrypted_key = encrypted_key[5:]

    # Decrypt using Windows DPAPI
    import ctypes.wintypes as wt

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    p = ctypes.create_string_buffer(encrypted_key, len(encrypted_key))
    blobin = DATA_BLOB(ctypes.sizeof(p), p)
    blobout = DATA_BLOB()
    retval = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blobin), None, None, None, None, 0, ctypes.byref(blobout)
    )
    if not retval:
        raise RuntimeError("DPAPI decryption failed")
    result = ctypes.string_at(blobout.pbData, blobout.cbData)
    ctypes.windll.kernel32.LocalFree(blobout.pbData)
    return result


def decrypt_cookie_value(ciphertext: bytes, key: bytes) -> str:
    """Decrypt a Chrome v10/v20 AES-GCM cookie."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if ciphertext[:3] in (b"v10", b"v20"):
        nonce = ciphertext[3:15]
        ct = ciphertext[15:]
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ct, None).decode("utf-8", errors="replace")
    return ciphertext.decode("utf-8", errors="replace")


def read_arena_cookies():
    cookies_path = os.path.expandvars(
        r"%LOCALAPPDATA%\Google\Chrome\User Data\Default\Network\Cookies"
    )
    tmp = tempfile.mktemp(suffix=".db")
    shutil.copy2(cookies_path, tmp)

    key = get_encryption_key()

    conn = sqlite3.connect(tmp)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT host_key, name, encrypted_value, path, expires_utc,
               is_secure, is_httponly, samesite
        FROM cookies
        WHERE host_key LIKE '%arena.ai%'
           OR host_key LIKE '%lmsys.org%'
    """)
    rows = cur.fetchall()
    conn.close()
    os.remove(tmp)

    cookies = []
    for row in rows:
        try:
            value = decrypt_cookie_value(row["encrypted_value"], key)
        except Exception as e:
            print(f"  [WARN] Could not decrypt cookie {row['name']}: {e}")
            value = ""
        cookies.append({
            "name": row["name"],
            "value": value,
            "domain": row["host_key"].lstrip("."),
            "path": row["path"],
            "secure": bool(row["is_secure"]),
            "httpOnly": bool(row["is_httponly"]),
            "sameSite": {-1: "Unspecified", 0: "None", 1: "Lax", 2: "Strict"}.get(row["samesite"], "Lax"),
        })
    return cookies


# ---------------------------------------------------------------------------
# Step 2: Inject cookies via CDP
# ---------------------------------------------------------------------------

async def inject_cookies(cookies, cdp_url="http://127.0.0.1:19333"):
    from playwright.async_api import async_playwright

    print(f"\n[CDP] Connecting to {cdp_url}...")
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(cdp_url)
        context = browser.contexts[0]

        print(f"[CDP] Injecting {len(cookies)} cookies...")
        for cookie in cookies:
            try:
                await context.add_cookies([cookie])
            except Exception as e:
                print(f"  [WARN] Failed to inject {cookie['name']}: {e}")

        print("[CDP] Navigating to arena.ai...")
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://arena.ai", wait_until="domcontentloaded")
        await asyncio.sleep(3)

        title = await page.title()
        url = page.url
        print(f"[RESULT] Title: {title}")
        print(f"[RESULT] URL:   {url}")

        # Screenshot to confirm login state
        shot_path = r"C:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR\scratch\arena_login_check.png"
        await page.screenshot(path=shot_path)
        print(f"[SCREENSHOT] Saved to {shot_path}")

        await browser.close()


if __name__ == "__main__":
    print("=== Arena Cookie Injector ===")
    print("[1] Reading cookies from real Chrome profile...")
    cookies = read_arena_cookies()
    print(f"    Found {len(cookies)} arena.ai cookies")
    for c in cookies:
        print(f"    - {c['name']} (domain={c['domain']})")

    print("\n[2] Injecting into CDP Chrome session...")
    asyncio.run(inject_cookies(cookies))
