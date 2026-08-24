import urllib.request
import json
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))

def compute_ema(series, period):
    k = 2.0 / (period + 1.0)
    ema = np.empty_like(series)
    ema[0] = series[0]
    for i in range(1, len(series)):
        ema[i] = series[i] * k + ema[i-1] * (1.0 - k)
    return ema

def compute_rma(series, period):
    rma = np.empty_like(series)
    alpha = 1.0 / period
    rma[period-1] = np.mean(series[:period])
    rma[:period-1] = rma[period-1]
    for i in range(period, len(series)):
        rma[i] = series[i] * alpha + rma[i-1] * (1.0 - alpha)
    return rma

def compute_rsi(closes, period=14):
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    gains = np.insert(gains, 0, 0.0)
    losses = np.insert(losses, 0, 0.0)
    avg_gain = compute_rma(gains, period)
    avg_loss = compute_rma(losses, period)
    rs = np.divide(avg_gain, avg_loss, out=np.zeros_like(avg_gain), where=avg_loss != 0)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi

def compute_atr(highs, lows, closes, period=14):
    tr1 = highs - lows
    tr2 = np.abs(highs - np.roll(closes, 1))
    tr3 = np.abs(lows - np.roll(closes, 1))
    tr2[0] = tr1[0]
    tr3[0] = tr1[0]
    tr = np.maximum(tr1, np.maximum(tr2, tr3))
    return compute_rma(tr, period)

def main():
    # 1. Fetch 1500 klines from Binance Futures
    url = "https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=15m&limit=1500"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as resp:
        raw_klines = json.loads(resp.read().decode('utf-8'))

    df = pd.DataFrame(raw_klines, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "count", "taker_buy_base", "taker_buy_quote", "ignore"
    ])

    for col in ["open", "high", "low", "close", "volume", "quote_volume", "taker_buy_base", "taker_buy_quote"]:
        df[col] = df[col].astype(float)
    df["count"] = df["count"].astype(int)

    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    quote_vols = df["quote_volume"].values
    base_vols = df["volume"].values
    tb_bases = df["taker_buy_base"].values

    # Technical Indicators
    df["ema_8"] = compute_ema(closes, 8)
    df["ema_21"] = compute_ema(closes, 21)
    df["ema_50"] = compute_ema(closes, 50)
    df["ema_200"] = compute_ema(closes, 200)
    df["ema_800"] = compute_ema(closes, 800)
    df["rsi_14"] = compute_rsi(closes, 14)
    df["atr_14"] = compute_atr(highs, lows, closes, 14)
    df["atr_100"] = compute_atr(highs, lows, closes, 100)
    df["volume_sma9"] = pd.Series(quote_vols).rolling(9).mean().fillna(df["quote_volume"]).values

    # Microstructure
    df["taker_sell_base"] = base_vols - tb_bases
    df["delta_btc"] = tb_bases - df["taker_sell_base"]
    df["tb_cnt"] = np.round(df["count"] * (tb_bases / base_vols)).astype(int)
    df["ts_cnt"] = df["count"] - df["tb_cnt"]
    df["cum_cvd_btc"] = np.cumsum(df["delta_btc"])

    # We select 2 completed candles from the last 3 hours
    # Currently index -1 is active candle (23:00-23:15 IST)
    # Candle A: index -5 (22:00:00 -> 22:14:59 IST)
    # Candle B: index -2 (22:45:00 -> 22:59:59 IST)
    
    idx_a = len(df) - 5
    idx_b = len(df) - 2

    for label, idx in [("Candle 1 (22:00 IST)", idx_a), ("Candle 2 (22:45 IST)", idx_b)]:
        row = df.iloc[idx]
        t_open = datetime.fromtimestamp(row["open_time"]/1000, tz=timezone.utc).astimezone(IST)
        t_close = datetime.fromtimestamp(row["close_time"]/1000, tz=timezone.utc).astimezone(IST)
        
        print(f"\n{'='*80}")
        print(f"  BINANCE HISTORICAL PIPELINE DATA DUMP — {label}")
        print(f"  Interval: {t_open.strftime('%Y-%m-%d %H:%M:%S IST')} -> {t_close.strftime('%H:%M:%S IST')}")
        print(f"{'='*80}")
        print(f"   1. ASSET          : BTCUSDT (Binance Futures)")
        print(f"   2. OPEN PRICE     : ${row['open']:,.1f}")
        print(f"   2. HIGH PRICE     : ${row['high']:,.1f}")
        print(f"   2. LOW PRICE      : ${row['low']:,.1f}")
        print(f"   2. CLOSE PRICE    : ${row['close']:,.1f}")
        print(f"   3. QUOTE VOLUME   : ${row['quote_volume']/1e6:.3f}M")
        print(f"   3. BASE VOLUME    : {row['volume']:,.2f} BTC")
        print(f"   3. VOLUME SMA 9   : ${row['volume_sma9']/1e6:.2f}M")
        print(f"   4. RSI (14)       : {row['rsi_14']:.2f}")
        print(f"   5. FUT CVD (15m)  : {row['delta_btc']:+,.2f} BTC")
        print(f"   5. FUT CVD (Roll) : {row['cum_cvd_btc']:+,.2f} BTC")
        print(f"  12. FP DELTA       : {row['delta_btc']:+,.4f} BTC")
        print(f"  19. TAKER BUY CNT  : {row['tb_cnt']:,} trades ({row['taker_buy_base']:,.2f} BTC)")
        print(f"  20. TAKER SELL CNT : -{row['ts_cnt']:,} trades ({row['taker_sell_base']:,.2f} BTC)")
        print(f"  21. EMA 8          : {row['ema_8']:,.1f}")
        print(f"  22. EMA 21         : {row['ema_21']:,.1f}")
        print(f"  23. EMA 50         : {row['ema_50']:,.1f}")
        print(f"  24. EMA 200        : {row['ema_200']:,.1f}")
        print(f"  25. EMA 800        : {row['ema_800']:,.1f}")
        print(f"  26. ATR 14         : {row['atr_14']:.1f}")
        print(f"  27. ATR 100        : {row['atr_100']:.1f}")
        print(f"  --. TRADE COUNT    : {row['count']:,}")
        print(f"{'='*80}")

if __name__ == "__main__":
    main()
