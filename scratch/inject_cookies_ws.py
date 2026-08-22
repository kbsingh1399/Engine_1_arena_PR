"""
inject_cookies_ws.py
Uses raw websocket CDP (no Playwright) to inject arena.ai cookies.
This bypasses any Playwright/Python 3.14 compatibility issues.
"""
import sqlite3
import shutil
import os
import json
import asyncio
import base64
import tempfile
import ctypes
import ctypes.wintypes as wt
import websocket
import urllib.request
import threading

# -----------------------------------------------------------------------
# DPAPI Decrypt
# -----------------------------------------------------------------------
class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

def dpapi_decrypt(ciphertext: bytes) -> bytes:
    p = ctypes.create_string_buffer(ciphertext, len(ciphertext))
    blobin = DATA_BLOB(ctypes.sizeof(p), p)
    blobout = DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blobin), None, None, None, None, 0, ctypes.byref(blobout)
    )
    if not ok:
        raise RuntimeError("DPAPI failed")
    result = ctypes.string_at(blobout.pbData, blobout.cbData)
    ctypes.windll.kernel32.LocalFree(blobout.pbData)
    return result

def get_aes_key() -> bytes:
    ls = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data\Local State")
    with open(ls, "r", encoding="utf-8") as f:
        state = json.load(f)
    enc_key = base64.b64decode(state["os_crypt"]["encrypted_key"])[5:]  # strip DPAPI prefix
    return dpapi_decrypt(enc_key)

def decrypt_value(ciphertext: bytes, key: bytes) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if not ciphertext:
        return ""
    if ciphertext[:3] in (b"v10", b"v20"):
        nonce, ct = ciphertext[3:15], ciphertext[15:]
        try:
            return AESGCM(key).decrypt(nonce, ct, None).decode("utf-8", errors="replace")
        except Exception as e:
            return f"[DECRYPT_ERROR:{e}]"
    try:
        return ciphertext.decode("utf-8", errors="replace")
    except Exception:
        return ""

def read_arena_cookies():
    cookies_path = os.path.expandvars(
        r"%LOCALAPPDATA%\Google\Chrome\User Data\Default\Network\Cookies"
    )
    tmp = tempfile.mktemp(suffix=".db")
    shutil.copy2(cookies_path, tmp)
    key = get_aes_key()
    conn = sqlite3.connect(tmp)
    conn.row_factory = sqlite3.Row
    cur = conn.execute("""
        SELECT host_key, name, encrypted_value, path, expires_utc,
               is_secure, is_httponly, samesite
        FROM cookies WHERE host_key LIKE '%arena.ai%' OR host_key LIKE '%auth.arena%'
    """)
    rows = cur.fetchall()
    conn.close()
    os.remove(tmp)
    cookies = []
    for row in rows:
        val = decrypt_value(bytes(row["encrypted_value"]), key)
        if not val or val.startswith("[DECRYPT_ERROR"):
            continue
        cookies.append({
            "name": row["name"],
            "value": val,
            "domain": row["host_key"],
            "path": row["path"],
            "secure": bool(row["is_secure"]),
            "httpOnly": bool(row["is_httponly"]),
            "sameSite": {-1: "None", 0: "None", 1: "Lax", 2: "Strict"}.get(row["samesite"], "Lax"),
        })
    return cookies

# -----------------------------------------------------------------------
# Raw CDP via websocket
# -----------------------------------------------------------------------
def get_ws_url(port=19333):
    resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list")
    pages = json.loads(resp.read())
    for p in pages:
        if p.get("type") == "page":
            return p["webSocketDebuggerUrl"]
    raise RuntimeError("No page tab found")

def cdp_send(ws_url, method, params=None):
    results = []
    done = threading.Event()
    def on_message(ws, msg):
        results.append(json.loads(msg))
        done.set()
    ws = websocket.WebSocketApp(ws_url, on_message=on_message)
    t = threading.Thread(target=ws.run_forever)
    t.daemon = True
    t.start()
    import time; time.sleep(0.5)
    ws.send(json.dumps({"id": 1, "method": method, "params": params or {}}))
    done.wait(timeout=5)
    ws.close()
    return results[0] if results else None

def inject_all_cookies(cookies, port=19333):
    ws_url = get_ws_url(port)
    print(f"  CDP WebSocket: {ws_url}")
    for c in cookies:
        result = cdp_send(ws_url, "Network.setCookie", c)
        ok = result.get("result", {}).get("success", False) if result else False
        status = "OK" if ok else "SKIP"
        print(f"  [{status}] {c['name']} = {c['value'][:30]}...")

if __name__ == "__main__":
    print("=== Arena Cookie Injector (Raw CDP) ===")
    
    print("[1] Decrypting cookies from real Chrome profile...")
    cookies = read_arena_cookies()
    print(f"    Decrypted {len(cookies)} valid cookies")
    for c in cookies:
        print(f"    - {c['name']}")

    if not cookies:
        print("[ERROR] No cookies decrypted. Check Chrome is fully closed and re-run.")
        exit(1)
    
    print("\n[2] Injecting via raw CDP websocket...")
    inject_all_cookies(cookies)
    
    print("\n[3] Navigating to arena.ai...")
    ws_url = get_ws_url()
    cdp_send(ws_url, "Page.navigate", {"url": "https://arena.ai"})
    import time; time.sleep(3)
    
    print("[DONE] Check your browser - if cookies were valid you should be logged in!")
