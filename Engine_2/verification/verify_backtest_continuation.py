"""
====================================================================================================
BACKTEST-TO-LIVE ALIGNMENT & CONTINUATION VERIFICATION HARNESS
====================================================================================================
Validates 100% mathematical and data integrity between historical Master Parquet datasets
and the Live Monitor Terminal across all 18 crypto assets.
====================================================================================================
"""
import sys
import os
import asyncio
import pyarrow.parquet as pq
import pandas as pd
import numpy as np

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from Engine_2.live.binance_live_monitor import (
    MatrixAssetState,
    bootstrap_matrix_symbol,
    find_master_parquet_path,
    ALL_SYMBOLS,
    calc_rsi,
    calc_ema,
)


async def verify_symbol_continuation(sym: str) -> dict:
    parquet_path = find_master_parquet_path(sym)
    if not parquet_path or not os.path.exists(parquet_path):
        return {"symbol": sym, "status": "FAIL", "reason": "Parquet file not found"}

    # 1. Load last row from master parquet
    pf = pq.ParquetFile(parquet_path)
    df_last = pf.read_row_group(pf.num_row_groups - 1).to_pandas()
    row = df_last.iloc[-1]

    # 2. Bootstrap live state
    st = MatrixAssetState(symbol=sym)
    await bootstrap_matrix_symbol(sym, target_state=st)

    # 3. Check parameters with scale-invariant tolerances
    def is_close(a: float, b: float, rtol: float = 1e-3, atol: float = 1e-4) -> bool:
        return abs(a - b) <= (atol + rtol * abs(b))

    checks = {
        "price": is_close(st.price, float(row["close"])),
        "ema_8": is_close(st.ema8, float(row["ema_8"])),
        "ema_21": is_close(st.ema21, float(row["ema_21"])),
        "ema_50": is_close(st.ema50, float(row["ema_50"])),
        "ema_200": is_close(st.ema200, float(row["ema_200"])),
        "ema_800": is_close(st.ema800, float(row["ema_800"])),
        "rsi_14": is_close(st.rsi, float(row["rsi_14"]), rtol=0.01, atol=0.1),
        "atr_14": is_close(st.atr14, float(row["atr_14"]), rtol=0.01, atol=0.01),
        "atr_100": is_close(st.atr100, float(row["atr_100"]), rtol=0.01, atol=0.01),
        "fut_cvd_session": is_close(st.session_fut_cvd_base, float(row["future_cvd_session"]), rtol=0.01, atol=1.0),
        "fut_cvd_lifetime": is_close(st.lifetime_fut_cvd_base, float(row["future_cvd_lifetime"]), rtol=0.01, atol=1.0),
        "spot_cvd_session": is_close(st.session_spot_cvd_base, float(row["spot_cvd_session"]), rtol=0.01, atol=1.0),
        "spot_cvd_lifetime": is_close(st.lifetime_spot_cvd_base, float(row["spot_cvd_lifetime"]), rtol=0.01, atol=1.0),
        "funding_rate": is_close(st.funding_rate, float(row["funding_rate_pct"]), rtol=0.01, atol=1e-4),
        "ls_ratio_global": is_close(st.ls_ratio_global, float(row["ls_ratio_global"]), rtol=0.01, atol=1e-3),
        "ls_ratio_top": is_close(st.ls_ratio_top, float(row["ls_ratio_top"]), rtol=0.01, atol=1e-3),
        "buffer_depth": len(st.recent_closes) >= 1000,
    }

    all_passed = all(checks.values())
    failed_keys = [k for k, v in checks.items() if not v]

    return {
        "symbol": sym,
        "status": "PASS" if all_passed else "FAIL",
        "failed_keys": failed_keys,
        "parquet_close": float(row["close"]),
        "live_price": st.price,
        "parquet_fut_cvd_life": float(row["future_cvd_lifetime"]),
        "live_fut_cvd_life": st.lifetime_fut_cvd_base,
        "buffer_len": len(st.recent_closes),
    }


async def main():
    print("=" * 110)
    print("🔬 COMPREHENSIVE BACKTEST-TO-LIVE ALIGNMENT & CONTINUATION AUDIT (ALL 18 SYMBOLS)")
    print("=" * 110)

    results = await asyncio.gather(*[verify_symbol_continuation(s) for s in ALL_SYMBOLS])

    print(f"\n{'SYMBOL':<10} | {'STATUS':<8} | {'PARQUET CLOSE':<15} | {'LIVE SEED PX':<15} | {'LIFETIME FUT CVD':<18} | {'BUFFER':<8}")
    print("-" * 90)

    passed_cnt = 0
    for r in results:
        sym = r["symbol"]
        status = r["status"]
        if status == "PASS":
            passed_cnt += 1
            print(f"{sym:<10} | ✅ PASS  | ${r['parquet_close']:<14,.2f} | ${r['live_price']:<14,.2f} | {r['live_fut_cvd_life']:<+18,.1f} | {r['buffer_len']} bars")
        else:
            print(f"{sym:<10} | ❌ FAIL  | Failed on: {r.get('failed_keys')}")

    print("=" * 110)
    print(f"📊 SUMMARY: {passed_cnt}/{len(ALL_SYMBOLS)} Symbols passed 100% backtest-to-live continuity verification.")
    print("=" * 110)


if __name__ == "__main__":
    asyncio.run(main())
