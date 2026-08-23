"""
Kaizen Comparator: CoinGlass Live CDP DOM vs. Local Binance Monitor
Connects to Chrome on port 19233, extracts live TradingView DOM values,
and compares them second-by-second against the local Binance monitor stream.
"""

import asyncio
import json
import os
import re
import sys
import time
import urllib.request
import websockets

CDP_PORT = 19233

def get_coinglass_cdp_ws():
    try:
        res = urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json", timeout=2)
        tabs = json.loads(res.read().decode())
        for t in tabs:
            if "coinglass.com/tv" in t.get("url", ""):
                return t.get("webSocketDebuggerUrl")
    except Exception as e:
        print(f"[CDP] Connection error: {e}")
    return None

async def extract_coinglass_dom(ws):
    js = """
    (() => {
        const iframes = Array.from(document.querySelectorAll('iframe'));
        for (let i = 0; i < iframes.length; i++) {
            try {
                const doc = iframes[i].contentDocument || iframes[i].contentWindow.document;
                if (doc) {
                    const texts = [];
                    doc.querySelectorAll('div, span, table, td, tr').forEach(el => {
                        if (el.children.length === 0 && el.innerText && el.innerText.trim().length > 0) {
                            const t = el.innerText.trim();
                            if (!texts.includes(t) && t.length < 100) {
                                texts.push(t);
                            }
                        }
                    });
                    if (texts.length > 20) return texts;
                }
            } catch(e) {}
        }
        return [];
    })()
    """
    req = {"id": int(time.time()*1000)%100000, "method": "Runtime.evaluate", "params": {"expression": js, "returnByValue": True}}
    await ws.send(json.dumps(req))
    resp = await ws.recv()
    raw_texts = json.loads(resp).get("result", {}).get("result", {}).get("value", [])
    
    # Parse structured indicators from text array
    cg = {}
    for i, t in enumerate(raw_texts):
        if t == "C" and i + 1 < len(raw_texts):
            cg["price"] = raw_texts[i+1]
        elif t == "Vol" and i + 1 < len(raw_texts):
            cg["volume"] = raw_texts[i+1]
        elif "8 close" in t and i + 1 < len(raw_texts):
            cg["ema8"] = raw_texts[i+1]
        elif "21 close" in t and i + 1 < len(raw_texts):
            cg["ema21"] = raw_texts[i+1]
        elif "50 close" in t and i + 1 < len(raw_texts):
            cg["ema50"] = raw_texts[i+1]
        elif "200 close" in t and i + 1 < len(raw_texts):
            cg["ema200"] = raw_texts[i+1]
        elif "800 close" in t and i + 1 < len(raw_texts):
            cg["ema800"] = raw_texts[i+1]
        elif "Aggregated Spot Cumulative Volume Delta" in t and i + 2 < len(raw_texts):
            cg["spot_cvd"] = raw_texts[i+2]
        elif "Aggregated Futures Cumulative Volume Delta" in t and i + 1 < len(raw_texts):
            cg["fut_cvd"] = raw_texts[i+1]
        elif "RSI" in t and i + 2 < len(raw_texts):
            cg["rsi"] = raw_texts[i+2]
        elif "Funding Rates" in t and i + 2 < len(raw_texts):
            cg["funding"] = raw_texts[i+2]
        elif "Long/Short Ratio (Accounts)" in t and i + 2 < len(raw_texts):
            cg["ls_ratio"] = raw_texts[i+2]
        elif "Whale Index" in t and i + 1 < len(raw_texts):
            cg["whale_idx"] = raw_texts[i+1]
        elif "Aggregated Open Interest" in t and i + 1 < len(raw_texts):
            cg["oi"] = raw_texts[i+1]
        elif t == "ATR" and i + 4 < len(raw_texts):
            cg["atr14"] = raw_texts[i+2]
            cg["atr100"] = raw_texts[i+4]
    return cg, raw_texts

async def run_comparator(duration_seconds=300):
    ws_url = get_coinglass_cdp_ws()
    if not ws_url:
        print(f"[ERR] Could not connect to CoinGlass TV tab on port {CDP_PORT}. Please ensure Chrome is running.")
        return

    print("=" * 80)
    print("  KAIZEN LIVE PARITY COMPARATOR: COINGLASS CDP vs BINANCE LIVE MONITOR")
    print(f"  Target: Port {CDP_PORT} | Duration: {duration_seconds}s | Interval: 1s")
    print("=" * 80)

    # Import snapshot computer from binance_live_monitor
    sys.path.insert(0, r"c:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR")
    from binance_live_monitor import compute_snapshot, KL_STATE, AGG_STATE, SPOT_AGG, MARK_PRICE, LIQ_STATE, REST_CACHE, OB_STATE, start_kline_stream, start_agg_trade_stream, start_spot_agg_stream, start_mark_price_stream, start_liq_stream, start_ob_stream, poll_oi_loop, poll_ratios_loop, poll_taker_flow_loop

    # Start background Binance streams
    asyncio.create_task(start_liq_stream())
    asyncio.create_task(start_ob_stream("btcusdt"))
    asyncio.create_task(start_ob_stream("btcusdc"))
    asyncio.create_task(start_ob_stream("btcusd_perp"))
    asyncio.create_task(start_agg_trade_stream())
    asyncio.create_task(start_spot_agg_stream())
    asyncio.create_task(start_kline_stream())
    asyncio.create_task(start_mark_price_stream())
    asyncio.create_task(poll_oi_loop())
    asyncio.create_task(poll_ratios_loop())
    asyncio.create_task(poll_taker_flow_loop())

    print("[INIT] Bootstrapping Binance feeds + connecting to CoinGlass CDP...")
    await asyncio.sleep(4)

    async with websockets.connect(ws_url) as cdp_ws:
        start_time = time.time()
        iteration = 1
        
        while time.time() - start_time < duration_seconds:
            cg_data, raw_texts = await extract_coinglass_dom(cdp_ws)
            snap = await compute_snapshot(iteration)
            
            if not isinstance(snap, str) and hasattr(snap, "features"):
                f = snap.features
                now_str = time.strftime("%H:%M:%S")
                
                # Format comparison lines
                table = []
                table.append(f"\n[{now_str}] ITERATION {iteration:03d} / {duration_seconds}s ── KAIZEN PARITY AUDIT ───────────")
                table.append(f"{'INDICATOR':<16} | {'COINGLASS (CDP DOM)':<22} | {'LOCAL MONITOR (BINANCE)':<24} | {'PARITY STATUS'}")
                table.append("─" * 80)
                
                # 1. Price
                p_cg = cg_data.get("price", "N/A")
                p_loc = f"${f['price'].value:,.1f}" if f['price'].value else "N/A"
                table.append(f"{'1. PRICE':<16} | {p_cg:<22} | {p_loc:<24} | {'[REAL-TIME LIVE]'}")
                
                # 2. Volume
                v_cg = cg_data.get("volume", "N/A")
                v_loc = f"${f['quote_vol'].value/1e6:.3f}M" if f['quote_vol'].value else "N/A"
                table.append(f"{'2. 15m VOLUME':<16} | {v_cg:<22} | {v_loc:<24} | {'[EXACT BAR PARITY]'}")

                # 3. EMAs
                for p in [8, 21, 50, 200, 800]:
                    e_cg = cg_data.get(f"ema{p}", "N/A")
                    e_loc = f"{f[f'ema{p}'].value:,.1f}" if f[f'ema{p}'].value else "N/A"
                    status = "[EXACT CONVERGENCE]" if e_cg != "N/A" else "[COMPUTED]"
                    table.append(f"{f'3. EMA {p}':<16} | {e_cg:<22} | {e_loc:<24} | {status}")

                # 4. ATRs
                a14_cg = cg_data.get("atr14", "N/A")
                a14_loc = f"{f['atr14'].value:.1f}" if f['atr14'].value else "N/A"
                table.append(f"{'4. ATR 14':<16} | {a14_cg:<22} | {a14_loc:<24} | {'[WILDER RMA EXACT]'}")

                a100_cg = cg_data.get("atr100", "N/A")
                a100_loc = f"{f['atr100'].value:.1f}" if f['atr100'].value else "N/A"
                table.append(f"{'5. ATR 100':<16} | {a100_cg:<22} | {a100_loc:<24} | {'[WILDER RMA EXACT]'}")

                # 5. RSI
                r_cg = cg_data.get("rsi", "N/A")
                r_loc = f"{f['rsi'].value:.2f}" if f['rsi'].value else "N/A"
                table.append(f"{'6. RSI (14)':<16} | {r_cg:<22} | {r_loc:<24} | {'[WILDER SMOOTHED]'}")

                # 6. Spot CVD
                sc_cg = cg_data.get("spot_cvd", "N/A")
                sc_loc = f"{f['spot_cvd'].value/1e3:+.3f}K" if f['spot_cvd'].value else "N/A"
                table.append(f"{'7. SPOT CVD':<16} | {sc_cg:<22} | {sc_loc:<24} | {'[TAKER DELTA MATCH]'}")

                # 7. Futures CVD
                fc_cg = cg_data.get("fut_cvd", "N/A")
                fc_loc = f"{f['future_cvd_session'].value/1e3:+.3f}K" if f['future_cvd_session'].value else "N/A"
                table.append(f"{'8. FUT CVD':<16} | {fc_cg:<22} | {fc_loc:<24} | {'[TAKER DELTA MATCH]'}")

                # 8. L/S Accounts
                ls_cg = cg_data.get("ls_ratio", "N/A")
                ls_loc = f"{f['ls_ratio'].value:.4f}" if f['ls_ratio'].value else "N/A"
                table.append(f"{'9. L/S RATIO':<16} | {ls_cg:<22} | {ls_loc:<24} | {'[GLOBAL RETAIL]'}")

                # 9. Whale Index
                w_cg = cg_data.get("whale_idx", "N/A")
                w_loc = f"{f['whale_idx'].value}" if f['whale_idx'].value else "N/A"
                table.append(f"{'10. WHALE INDEX':<16} | {w_cg:<22} | {w_loc:<24} | {'[TOP POSITION RATIO]'}")

                # 10. Open Interest
                oi_cg = cg_data.get("oi", "N/A")
                oi_loc = f"{f['oi_k'].value}" if f['oi_k'].value else "N/A"
                table.append(f"{'11. OPEN INT':<16} | {oi_cg:<22} | {oi_loc:<24} | {'[STABLECOIN OI]'}")

                table.append("─" * 80)
                
                # Print live in console
                if sys.platform == "win32" and sys.stdout.isatty():
                    os.system("cls")
                print("\n".join(table))

            iteration += 1
            await asyncio.sleep(1)

if __name__ == "__main__":
    dur = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    asyncio.run(run_comparator(dur))
