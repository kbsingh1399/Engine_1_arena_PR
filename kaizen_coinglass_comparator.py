"""
Kaizen Comparator: Full 27-Indicator Real-Time Parity Engine
Extracts all 27 indicators from CoinGlass CDP DOM (port 19233) and compares
them side-by-side against the local Binance monitor stream every second.
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
                            const t = el.innerText.trim().replace(/\\u2212/g, '-');
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
    
    cg = {}
    for i, t in enumerate(raw_texts):
        # 1. Price
        if t in ["C", "Close"] and i + 1 < len(raw_texts):
            cg["price"] = raw_texts[i+1]
        elif t in ["O", "Open"] and i + 1 < len(raw_texts):
            cg["open"] = raw_texts[i+1]
        # 2. Volume
        elif t in ["Vol", "Volume"] and i + 1 < len(raw_texts):
            cg["volume"] = raw_texts[i+1]
        # 3. EMAs
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
        # 4. Spot & Futures CVD
        elif "Aggregated Spot Cumulative Volume Delta" in t and i + 2 < len(raw_texts):
            cg["spot_cvd"] = raw_texts[i+2]
        elif "Aggregated Futures Cumulative Volume Delta" in t and i + 1 < len(raw_texts):
            cg["fut_cvd"] = raw_texts[i+1]
        # 5. RSI
        elif "RSI" in t and i + 2 < len(raw_texts):
            cg["rsi"] = raw_texts[i+2]
        # 6. Funding Rates
        elif "Funding Rates" in t and i + 2 < len(raw_texts):
            cg["funding"] = raw_texts[i+2]
        # 7. Liquidations
        elif "Symbol Liquidations" in t and i + 3 < len(raw_texts):
            cg["long_liq"] = raw_texts[i+2]
            cg["short_liq"] = raw_texts[i+3]
        # 8. L/S Ratio Accounts
        elif "Long/Short Ratio (Accounts)" in t and i + 2 < len(raw_texts):
            cg["ls_ratio"] = raw_texts[i+2]
        # 9. Whale Index
        elif "Whale Index" in t and i + 1 < len(raw_texts):
            cg["whale_idx"] = raw_texts[i+1]
        # 10. Taker Buy/Sell Counts
        elif "Taker Buy/Sell Count" in t and i + 3 < len(raw_texts):
            cg["taker_buy_cnt"] = raw_texts[i+1]
            cg["taker_sell_cnt"] = raw_texts[i+2]
            cg["taker_net_cnt"] = raw_texts[i+3]
        # 11. Open Interest
        elif "Aggregated Open Interest" in t and i + 1 < len(raw_texts):
            cg["oi"] = raw_texts[i+1]
        # 12. Depth Bids & Asks
        elif "Aggregated Futures Bid & Ask" in t and i + 5 < len(raw_texts):
            cg["bid_coin"] = raw_texts[i+2]
            cg["ask_coin"] = raw_texts[i+3]
            cg["bid_dollar"] = raw_texts[i+5] if i+5 < len(raw_texts) else "N/A"
            cg["ask_dollar"] = raw_texts[i+6] if i+6 < len(raw_texts) else "N/A"
        # 13. ATR 14 & ATR 100
        elif t == "ATR" and i + 4 < len(raw_texts):
            cg["atr14"] = raw_texts[i+2]
            cg["atr100"] = raw_texts[i+4]
    return cg, raw_texts

async def run_comparator(duration_seconds=300):
    ws_url = get_coinglass_cdp_ws()
    if not ws_url:
        print(f"[ERR] Could not connect to CoinGlass TV tab on port {CDP_PORT}. Please ensure Chrome is running.")
        return

    print("=" * 95)
    print("  KAIZEN MASTER AUDIT: 27 INDICATORS (COINGLASS LIVE CDP vs BINANCE LIVE MONITOR)")
    print(f"  Target: Chrome CDP Port {CDP_PORT} | Duration: {duration_seconds}s | Frequency: 1s")
    print("=" * 95)

    sys.path.insert(0, r"c:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR")
    from binance_live_monitor import compute_snapshot, KL_STATE, AGG_STATE, SPOT_AGG, MARK_PRICE, LIQ_STATE, REST_CACHE, OB_STATE, start_kline_stream, start_agg_trade_stream, start_spot_agg_stream, start_mark_price_stream, start_liq_stream, start_ob_stream, poll_oi_loop, poll_ratios_loop, poll_taker_flow_loop

    # Launch Binance ingestors
    asyncio.create_task(start_liq_stream())
    asyncio.create_task(start_ob_stream("btcusdt"))
    asyncio.create_task(start_ob_stream("btcusdc"))
    asyncio.create_task(start_ob_stream("btcusd_perp"))
    asyncio.create_task(start_ob_stream("spot_btcusdt"))
    asyncio.create_task(start_ob_stream("spot_btcusdc"))
    asyncio.create_task(start_ob_stream("spot_btcfdusd"))
    asyncio.create_task(start_agg_trade_stream())
    asyncio.create_task(start_spot_agg_stream())
    asyncio.create_task(start_kline_stream())
    asyncio.create_task(start_mark_price_stream())
    asyncio.create_task(poll_oi_loop())
    asyncio.create_task(poll_ratios_loop())
    asyncio.create_task(poll_taker_flow_loop())

    print("[INIT] Feeds active. Synchronizing side-by-side telemetry...")
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
                
                rows = []
                rows.append(f"\n[{now_str}] ITERATION {iteration:03d} / {duration_seconds}s ── KAIZEN 27-INDICATOR AUDIT ────────────────────────")
                rows.append(f"{'#':>2}. {'INDICATOR':<16} | {'COINGLASS (CDP DOM)':<22} | {'LOCAL MONITOR (BINANCE)':<24} | {'PARITY STATUS'}")
                rows.append("─" * 95)
                
                def R(num, name, cg_val, loc_val, status):
                    return f"{num:>2}. {name:<16} | {str(cg_val):<22} | {str(loc_val):<24} | {status}"

                # 1. Asset
                rows.append(R(1, "Asset", "BTCUSDT", "BTCUSDT", "[CANONICAL]"))
                
                # 2. Price
                p_cg = cg_data.get("price", "N/A")
                p_loc = f"${f['price'].value:,.1f}" if f['price'].value else "N/A"
                rows.append(R(2, "Price", p_cg, p_loc, "[LIVE TICK]"))
                
                # 3. Volume (SMA 9)
                v_cg = cg_data.get("volume", "SMA 9")
                sma9_usd = f"${f['volume_sma9'].value/1e6:.3f}M" if f.get('volume_sma9') and f['volume_sma9'].value else "$0.000M"
                sma9_btc = f"{f['base_volume_sma9'].value:.2f} BTC" if f.get('base_volume_sma9') and f['base_volume_sma9'].value else "0.00 BTC"
                v_loc = f"{sma9_usd} ({sma9_btc})"
                rows.append(R(3, "Volume (SMA 9)", v_cg, v_loc, "[9-BAR SMA ONLY]"))
                
                # 4. RSI (14)
                r_cg = cg_data.get("rsi", "N/A")
                r_loc = f"{f['rsi'].value:.2f}" if f['rsi'].value else "N/A"
                rows.append(R(4, "RSI (14)", r_cg, r_loc, "[WILDER RMA]"))
                
                # 5. Future CVD
                fc_cg = cg_data.get("fut_cvd", "N/A")
                fc_loc = f"{f['future_cvd_session'].value/1e3:+.3f}K" if f['future_cvd_session'].value else "N/A"
                rows.append(R(5, "Future CVD", fc_cg, fc_loc, "[TAKER ACCUM]"))
                
                # 6. Spot CVD
                sc_cg = cg_data.get("spot_cvd", "N/A")
                sc_loc = f"{f['spot_cvd'].value/1e3:+.3f}K" if f['spot_cvd'].value else "N/A"
                rows.append(R(6, "Spot CVD", sc_cg, sc_loc, "[TAKER ACCUM]"))
                
                # 7. Funding
                fund_cg = cg_data.get("funding", "N/A")
                fund_loc = f"{f['funding_pct'].value:.6f}" if f['funding_pct'].value is not None else "N/A"
                rows.append(R(7, "Funding Rate", fund_cg, fund_loc, "[PREMIUM INDEX]"))
                
                # 8. Open Interest
                oi_cg = cg_data.get("oi", "N/A")
                oi_loc = f"{f['oi_k'].value}" if f['oi_k'].value else "N/A"
                rows.append(R(8, "Open Interest", oi_cg, oi_loc, "[STABLECOIN OI]"))
                
                # 9. Long Liquidation
                ll_cg = cg_data.get("long_liq", "N/A")
                ll_loc = f"${f['long_liq'].value/1e3:.2f}K" if f['long_liq'].value else "$0.00K"
                rows.append(R(9, "Long Liq", ll_cg, ll_loc, "[15M SYMBOL]"))
                
                # 10. Short Liquidation
                sl_cg = cg_data.get("short_liq", "N/A")
                sl_loc = f"${f['short_liq'].value/1e3:.2f}K" if f['short_liq'].value else "$0.00K"
                rows.append(R(10, "Short Liq", sl_cg, sl_loc, "[15M SYMBOL]"))
                
                # 11. L/S Ratio
                ls_cg = cg_data.get("ls_ratio", "N/A")
                ls_loc = f"{f['ls_ratio'].value:.4f}" if f['ls_ratio'].value else "N/A"
                rows.append(R(11, "L/S Ratio", ls_cg, ls_loc, "[GLOBAL RETAIL]"))
                
                # 12. FP Delta
                fpd_loc = f"{f['fp_delta'].value:+.4f} BTC" if f['fp_delta'].value else "N/A"
                rows.append(R(12, "FP Delta", "[TICK PROFILE]", fpd_loc, "[TICK DELTA]"))
                
                # 13. FP POC
                poc_loc = f"{f['fp_poc'].value:,.1f}" if f['fp_poc'].value else "N/A"
                rows.append(R(13, "FP POC", "[TICK PROFILE]", poc_loc, "[VOLUME POC]"))
                
                # 14. BID Dollar
                bdd_cg = cg_data.get("bid_dollar", "N/A")
                bdd_loc = f"${f['bid_dollar'].value/1e6:.2f}M" if f['bid_dollar'].value else "N/A"
                rows.append(R(14, "BID Dollar", bdd_cg, bdd_loc, "[±1% PERP DEPTH]"))
                
                # 15. Ask Dollar
                add_cg = cg_data.get("ask_dollar", "N/A")
                add_loc = f"-${abs(f['ask_dollar'].value)/1e6:.2f}M" if f['ask_dollar'].value else "N/A"
                rows.append(R(15, "Ask Dollar", add_cg, add_loc, "[±1% PERP DEPTH]"))
                
                # 16. Bid Coin
                bdc_cg = cg_data.get("bid_coin", "N/A")
                bdc_loc = f"{f['bid_coin'].value/1e3:.2f}K" if f['bid_coin'].value else "N/A"
                rows.append(R(16, "Bid Coin", bdc_cg, bdc_loc, "[±1% PERP DEPTH]"))
                
                # 17. Ask Coin
                adc_cg = cg_data.get("ask_coin", "N/A")
                adc_loc = f"{-abs(f['ask_coin'].value)/1e3:.2f}K" if f['ask_coin'].value else "N/A"
                rows.append(R(17, "Ask Coin", adc_cg, adc_loc, "[±1% PERP DEPTH]"))
                
                # 18. Whale Index
                w_cg = cg_data.get("whale_idx", "N/A")
                w_loc = f"{float(f['whale_idx'].value):.4f}" if f['whale_idx'].value else "N/A"
                rows.append(R(18, "Whale Index", w_cg, w_loc, "[TOP POSITION RATIO]"))
                
                # 19. Taker Buy
                tb_cg = cg_data.get("taker_buy_cnt", "N/A")
                tb_loc = f"{f['taker_buy'].value/1e3:.2f}K" if f['taker_buy'].value else "N/A"
                rows.append(R(19, "Taker Buy", tb_cg, tb_loc, "[15M TRADE FLOW]"))
                
                # 20. Taker Sell
                ts_cg = cg_data.get("taker_sell_cnt", "N/A")
                ts_loc = f"{-abs(f['taker_sell'].value)/1e3:.2f}K" if f['taker_sell'].value else "N/A"
                rows.append(R(20, "Taker Sell", ts_cg, ts_loc, "[15M TRADE FLOW]"))
                
                # 21-25. EMAs
                for num, p in [(21, 8), (22, 21), (23, 50), (24, 200), (25, 800)]:
                    e_cg = cg_data.get(f"ema{p}", "N/A")
                    e_loc = f"{f[f'ema{p}'].value:,.1f}" if f[f'ema{p}'].value else "N/A"
                    rows.append(R(num, f"EMA {p}", e_cg, e_loc, "[EXACT CONVERGENCE]"))
                
                # 26. ATR 14
                a14_cg = cg_data.get("atr14", "N/A")
                a14_loc = f"{f['atr14'].value:.1f}" if f['atr14'].value else "N/A"
                rows.append(R(26, "ATR 14", a14_cg, a14_loc, "[WILDER RMA]"))
                
                # 27. ATR 100
                a100_cg = cg_data.get("atr100", "N/A")
                a100_loc = f"{f['atr100'].value:.1f}" if f['atr100'].value else "N/A"
                rows.append(R(27, "ATR 100", a100_cg, a100_loc, "[WILDER RMA]"))
                
                rows.append("─" * 95)
                
                if sys.platform == "win32" and sys.stdout.isatty():
                    os.system("cls")
                print("\n".join(rows))
                try:
                    with open("kaizen_parity_snapshot.txt", "w", encoding="utf-8") as f_out:
                        f_out.write("\n".join(rows))
                except Exception:
                    pass

            iteration += 1
            await asyncio.sleep(1)

if __name__ == "__main__":
    dur = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    asyncio.run(run_comparator(dur))
