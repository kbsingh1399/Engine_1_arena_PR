"""
LIVE BINANCE API MONITOR
Covers 27 indicators using strictly Binance API logic.
"""

import asyncio, json, sys, time, urllib.request, websockets
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

LIQ_STATE = {"current_candle_ts": 0, "long_liq_usd": 0.0, "short_liq_usd": 0.0, "bootstrapped": False}

# Full live orderbook maintained via WebSocket snapshot+diff
OB_STATE = {
    "btcusdt": {"bids": {}, "asks": {}, "last_update_id": 0, "ready": False},
    "btcusdc": {"bids": {}, "asks": {}, "last_update_id": 0, "ready": False},
    "btcusd_perp": {"bids": {}, "asks": {}, "last_update_id": 0, "ready": False},
}


async def binance_liquidation_listener():
    url = "wss://fstream.binance.com/stream?streams=btcusdt@forceOrder/btcusdc@forceOrder"
    try:
        async with websockets.connect(url, max_size=10*1024*1024) as ws:
            while True:
                try:
                    data = json.loads(await asyncio.wait_for(ws.recv(), timeout=1.0))
                    o = data.get("data", {}).get("o", {})
                    if o:
                        side = o.get("S"); qty = float(o.get("q",0)); price = float(o.get("p",0))
                        notional = qty * price
                        ts = (int(o.get("T", time.time()*1000)) // 1000 // 900) * 900
                        if ts != LIQ_STATE["current_candle_ts"]:
                            LIQ_STATE.update({"current_candle_ts": ts, "long_liq_usd": 0.0, "short_liq_usd": 0.0, "bootstrapped": False})
                        if side == "SELL": LIQ_STATE["long_liq_usd"] += notional
                        elif side == "BUY": LIQ_STATE["short_liq_usd"] += notional
                except asyncio.TimeoutError:
                    continue
    except (asyncio.CancelledError, Exception):
        return


async def binance_orderbook_listener(symbol, stream_type):
    """Maintain full local Binance BTC futures orderbook via snapshot+diff WebSocket."""
    url_base = "https://fapi.binance.com/fapi/v1/depth" if stream_type == "f" else "https://dapi.binance.com/dapi/v1/depth"
    ws_base = "wss://fstream.binance.com/ws" if stream_type == "f" else "wss://dstream.binance.com/ws"
    
    while True:
        try:
            OB_STATE[symbol]["ready"] = False
            # 1. Full snapshot (max 1000 levels) as seed
            snap = json.loads(urllib.request.urlopen(
                f"{url_base}?symbol={symbol.upper()}&limit=1000", timeout=10
            ).read())
            OB_STATE[symbol]["bids"] = {p: float(q) for p, q in snap["bids"] if float(q) > 0}
            OB_STATE[symbol]["asks"] = {p: float(q) for p, q in snap["asks"] if float(q) > 0}
            OB_STATE[symbol]["last_update_id"] = snap["lastUpdateId"]
            OB_STATE[symbol]["ready"] = True
            # 2. Apply live diff stream on top of snapshot
            async with websockets.connect(
                f"{ws_base}/{symbol}@depth",
                max_size=10 * 1024 * 1024
            ) as ws:
                async for raw in ws:
                    ev = json.loads(raw)
                    # Drop stale events that predate snapshot
                    if ev.get("u", 0) <= OB_STATE[symbol]["last_update_id"]:
                        continue
                    for px, qty in ev.get("b", []):
                        if float(qty) == 0:
                            OB_STATE[symbol]["bids"].pop(px, None)
                        else:
                            OB_STATE[symbol]["bids"][px] = float(qty)
                    for px, qty in ev.get("a", []):
                        if float(qty) == 0:
                            OB_STATE[symbol]["asks"].pop(px, None)
                        else:
                            OB_STATE[symbol]["asks"][px] = float(qty)
                    OB_STATE[symbol]["last_update_id"] = ev["u"]
        except (asyncio.CancelledError):
            return
        except Exception:
            await asyncio.sleep(1)
            continue


def get_depth_within_pct(current_price, pct=0.01):
    """Sum bids/asks within ±pct of current_price across USDT-M, USDC-M, and COIN-M."""
    if not current_price:
        return None, None, None, None
    bid_min = current_price * (1 - pct)
    ask_max = current_price * (1 + pct)
    bid_coin = 0.0; ask_coin = 0.0; bid_dol = 0.0; ask_dol = 0.0
    
    for sym in ["btcusdt", "btcusdc", "btcusd_perp"]:
        if not OB_STATE[sym]["ready"]: continue
        is_coinm = (sym == "btcusd_perp")
        
        for px_str, qty in OB_STATE[sym]["bids"].items():
            px = float(px_str)
            if px >= bid_min:
                qty_btc = (qty * 100 / px) if is_coinm else qty
                bid_coin += qty_btc
                bid_dol += (qty * 100) if is_coinm else (px * qty_btc)
                
        for px_str, qty in OB_STATE[sym]["asks"].items():
            px = float(px_str)
            if px <= ask_max:
                qty_btc = (qty * 100 / px) if is_coinm else qty
                ask_coin += qty_btc
                ask_dol += (qty * 100) if is_coinm else (px * qty_btc)
                
    return bid_coin, ask_coin, bid_dol, ask_dol


def fetch(url, timeout=5):
    return json.loads(urllib.request.urlopen(url, timeout=timeout).read().decode())


def calc_ema(closes, period):
    if len(closes) < period: return None
    k = 2.0 / (period + 1)
    ema = sum(closes[:period]) / period
    for c in closes[period:]: ema = c*k + ema*(1-k)
    return ema


def calc_atr(kl, period):
    if len(kl) < period+1: return None
    trs = [max(float(kl[i][2])-float(kl[i][3]), abs(float(kl[i][2])-float(kl[i-1][4])), abs(float(kl[i][3])-float(kl[i-1][4]))) for i in range(1,len(kl))]
    if len(trs) < period: return None
    atr = sum(trs[:period]) / period
    for tr in trs[period:]: atr = (atr*(period-1) + tr) / period
    return atr


def compute_binance_metrics(bar_count=500):
    try:
        # ── 1. Latest 1000 bars (no startTime) — for RSI, EMA, ATR, current bar ───
        kf_latest  = fetch("https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=15m&limit=1000")
        kf_spot    = fetch("https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=15m&limit=1000")

        lf = kf_latest[-1]  # current (open) candle
        closes = [float(k[4]) for k in kf_latest]
        close_price = closes[-1]
        quote_vol = float(lf[7])

        # RSI(14) Wilder
        gains, losses = [], []
        for i in range(1, len(closes)):
            d = closes[i] - closes[i-1]
            gains.append(max(d,0.0)); losses.append(max(-d,0.0))
        ag = sum(gains[:14])/14; al = sum(losses[:14])/14
        for i in range(14, len(gains)):
            ag=(ag*13+gains[i])/14; al=(al*13+losses[i])/14
        rsi = 100.0 - 100.0/(1+ag/al) if al>0 else 100.0

        # EMAs (need up to 800 bars)
        e8=calc_ema(closes,8); e21=calc_ema(closes,21); e50=calc_ema(closes,50)
        e200=calc_ema(closes,200); e800=calc_ema(closes,800)

        # ATRs
        a14=calc_atr(kf_latest,14); a100=calc_atr(kf_latest,100)

        # FP POC = (H+L)/2 current bar
        fp_poc = (float(lf[2])+float(lf[3]))/2.0

        # Taker buy/sell current bar (aggregate USDT-M, USDC-M, COIN-M)
        tb = float(lf[9]); ts = float(lf[5]) - tb
        try:
            kuc = fetch("https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDC&interval=15m&limit=1", 3)
            tb += float(kuc[-1][9]); ts += float(kuc[-1][5]) - float(kuc[-1][9])
        except Exception: pass
        try:
            kcm = fetch("https://dapi.binance.com/dapi/v1/klines?symbol=BTCUSD_PERP&interval=15m&limit=1", 3)
            tb += float(kcm[-1][10]); ts += float(kcm[-1][7]) - float(kcm[-1][10])
        except Exception: pass
        
        # Whale Index / Top Trader proxy from Binance
        bn_whale = "N/A"
        try:
            top_pos = fetch("https://fapi.binance.com/futures/data/topLongShortPositionRatio?symbol=BTCUSDT&period=15m&limit=1")
            top_acc = fetch("https://fapi.binance.com/futures/data/topLongShortAccountRatio?symbol=BTCUSDT&period=15m&limit=1")
            if top_pos and top_acc:
                bn_whale = f"Pos: {top_pos[0]['longShortRatio']} | Acc: {top_acc[0]['longShortRatio']}"
        except Exception: pass

        # ── 2. Viewport-aligned bars — for CVD ──────────
        lim_cvd = min(max(bar_count, 500), 1000)
        kf_cvd  = kf_latest
        kuc_cvd = fetch(f"https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDC&interval=15m&limit={lim_cvd}")
        ks_cvd  = kf_spot

        def dlt(kl): return [float(k[9])-(float(k[5])-float(k[9])) for k in kl]
        fcvd = sum(dlt(kf_cvd)) + sum(dlt(kuc_cvd))
        scvd = sum(dlt(ks_cvd))

        prem = fetch("https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT", 4)
        funding = float(prem.get("lastFundingRate",0))*100.0
        
        # FP Delta (Footprint Delta) is Taker Buy - Taker Sell for the current 15m candle (BTCUSDT only)
        tb_usdt = float(lf[9])
        ts_usdt = float(lf[5]) - tb_usdt
        fp_delta = tb_usdt - ts_usdt
        
        # OI
        oi_t = float(fetch("https://fapi.binance.com/fapi/v1/openInterest?symbol=BTCUSDT",4).get("openInterest",0))
        oi_c = float(fetch("https://fapi.binance.com/fapi/v1/openInterest?symbol=BTCUSDC",4).get("openInterest",0))
        oi_k = (oi_t+oi_c)/1e3
        
        # L/S Ratio
        ls_d = fetch("https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol=BTCUSDT&period=15m&limit=1",4)
        ls_ratio = float(ls_d[0]["longShortRatio"]) if ls_d else None
        
        # Order book — full ±1% depth from live WebSocket orderbook (OB_STATE)
        bid_coin, ask_coin, bid_dol, ask_dol = get_depth_within_pct(close_price, pct=0.01)
        
        return {"asset":"BTCUSDT","price":close_price,"quote_vol":quote_vol,"vol_m":f"{quote_vol/1e6:.3f}M",
                "ask_dol": ask_dol, "ask_coin": ask_coin, "whale_idx": bn_whale, "taker_buy": tb, "taker_sell": ts,
                "rsi":rsi,"future_cvd":fcvd,"spot_cvd":scvd,
                "funding_pct":funding,"oi_k":oi_k,"ls_ratio":ls_ratio,"fp_delta":fp_delta,"fp_poc":fp_poc,
                "bid_dollar":bid_dol,"ask_dollar":ask_dol,"bid_coin":bid_coin,"ask_coin":ask_coin,
                "ema8":e8,"ema21":e21,"ema50":e50,"ema200":e200,"ema800":e800,"atr14":a14,"atr100":a100}
    except Exception as e:
        return {"error": str(e)}


def fmt_usd(v):
    if v is None: return "N/A"
    a = abs(v)
    if a>=1e6: return f"${a/1e6:.3f}M"
    if a>=1e3: return f"${a/1e3:.2f}K"
    return f"${a:.2f}"

def fmt_btc(v):
    if v is None: return "N/A"
    a = abs(v)
    if a>=1e3: return f"{a/1e3:.2f}K"
    return f"{a:.3f}"

def R(n, label, bn, note=""):
    return f"  {n:>2}. {label:<13} | {bn:<14} | {note}"


async def run_live_comparison():
    print("="*80)
    print("  LIVE BINANCE API MONITOR — 27 INDICATORS (No CoinGlass)")
    print("="*80)
    liq_task = None; ob_tasks = []
    if "--once" not in sys.argv:
        liq_task = asyncio.create_task(binance_liquidation_listener())
        ob_tasks = [
            asyncio.create_task(binance_orderbook_listener("btcusdt", "f")),
            asyncio.create_task(binance_orderbook_listener("btcusdc", "f")),
            asyncio.create_task(binance_orderbook_listener("btcusd_perp", "d"))
        ]
        print("[INIT] Fetching orderbook snapshots across 3 pairs... (may take 2-3s)")
        await asyncio.sleep(3)  # Let OB_STATE seed before first tick
    
    print("[CONNECTED] Binance API Monitor Active.\n")
    try:
        while True:
            t = datetime.now().strftime("%H:%M:%S")
            bn = compute_binance_metrics(500)
            if "error" in bn:
                print(f"[{t}] BN error: {bn['error']}"); await asyncio.sleep(3); continue
                
            # ── liquidation ─────────────────────────────────────────
            bn_ll = LIQ_STATE["long_liq_usd"]
            bn_sl = LIQ_STATE["short_liq_usd"]
            
            # ── values ───────────────────────────────────────────────────────
            bn_p  = bn.get("price",0.0)
            bn_rsi=bn.get("rsi")
            bn_fc=bn.get("future_cvd")
            bn_sc=bn.get("spot_cvd")
            bn_oi=bn.get("oi_k")
            bn_ls=bn.get("ls_ratio")
            bn_bd=bn.get("bid_dollar")
            bn_ad=bn.get("ask_dollar")
            bn_bc=bn.get("bid_coin")
            bn_ac=bn.get("ask_coin")
            bn_tb=bn.get("taker_buy")
            bn_ts=bn.get("taker_sell")
            bn_fpd=bn.get("fp_delta")
            bn_poc=bn.get("fp_poc")
            bn_fund=bn.get("funding_pct")
            wh=bn.get("whale_idx", "N/A")
            
            def ef(k_bn):
                bv=bn.get(k_bn)
                return f"{bv:,.2f}" if bv else "N/A"
            e8=ef("ema8"); e21=ef("ema21"); e50=ef("ema50")
            e200=ef("ema200"); e800=ef("ema800")
            def af(k_bn):
                bv=bn.get(k_bn)
                return f"{bv:.4f}" if bv else "N/A"
            a14=af("atr14"); a100=af("atr100")
            
            # ── print ─────────────────────────────────────────────────────────
            print(f"\n[{t}] " + "─"*65)
            print(R(" 1","ASSET",      "BTCUSDT",       "Binance Futures"))
            print(R(" 2","PRICE",      f"${bn_p:,.2f}", ""))
            print(R(" 3","VOLUME",     bn.get("vol_m","N/A"), f"USDT ${bn.get('quote_vol',0):,.0f}"))
            print(R(" 4","RSI (14)",   f"{bn_rsi:.2f}" if bn_rsi else "N/A", ""))
            print(R(" 5","FUTURE CVD", f"{bn_fc/1e3:.3f}K" if bn_fc else "N/A", ""))
            print(R(" 6","SPOT CVD",   f"{bn_sc/1e3:.3f}K" if bn_sc else "N/A", ""))
            print(R(" 7","FUNDING %",  f"{bn_fund:.6f}" if bn_fund else "N/A", "Premium Index Rate"))
            print(R(" 8","OPEN INT",   f"{bn_oi:.3f}K" if bn_oi else "N/A", "USDT+USDC pairs"))
            print(R(" 9","LONG LIQ",   fmt_usd(bn_ll), "(Bootstrap+Stream)"))
            print(R("10","SHORT LIQ",  fmt_usd(bn_sl), "(Bootstrap+Stream)"))
            print(R("11","L/S RATIO",  f"{bn_ls:.4f}" if bn_ls else "N/A", "Global Account Ratio"))
            print(R("12","FP DELTA",   f"{bn_fpd:+.4f}" if bn_fpd else "N/A", "Footprint (BTCUSDT)"))
            print(R("13","FP POC",     f"{bn_poc:,.2f}" if bn_poc else "N/A", "(H+L)/2 cur bar"))
            print(R("14","BID DOLLAR", fmt_usd(bn_bd), "BN ±1%"))
            print(R("15","ASK DOLLAR", fmt_usd(bn_ad), "BN ±1%"))
            print(R("16","BID COIN",   fmt_btc(bn_bc), "BN ±1%"))
            print(R("17","ASK COIN",   fmt_btc(bn_ac), "BN ±1%"))
            print(R("18","WHALE IDX",  wh, "Top Trader Ratios"))
            print(R("19","TAKER BUY",  fmt_btc(bn_tb), "Partial-bar (All pairs)"))
            print(R("20","TAKER SELL", fmt_btc(bn_ts), "Partial-bar (All pairs)"))
            print(R("21","EMA 8",      e8))
            print(R("22","EMA 21",     e21))
            print(R("23","EMA 50",     e50))
            print(R("24","EMA 200",    e200))
            print(R("25","EMA 800",    e800))
            print(R("26","ATR 14",     a14))
            print(R("27","ATR 100",    a100))
            sys.stdout.flush()
            if "--once" in sys.argv: break
            await asyncio.sleep(3)
    finally:
        for t in [liq_task] + ob_tasks:
            if t:
                t.cancel()
                try: await t
                except asyncio.CancelledError: pass


if __name__ == "__main__":
    try: asyncio.run(run_live_comparison())
    except (KeyboardInterrupt, asyncio.CancelledError): print("\n[STOPPED] Monitor exited cleanly.")
