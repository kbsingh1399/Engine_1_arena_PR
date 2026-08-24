# Gate 4: 15-Minute Candle Boundary Auto-Rollover & State Reset Protocol

**Verification Timestamp**: 2026-08-24 22:54:00  
**Standard**: FABLE 5 Protocol Part 12 & .okf/indicators/candle_rollover.md

---

## 1. Boundary Trigger & Zero-Reset Verification

Binance 15-minute candles begin strictly at Unix epoch millisecond boundaries where $\text{ts} \pmod{900\,000} = 0$ (e.g. `:00`, `:15`, `:30`, `:45`).

| Indicator / Metric | Boundary Action (:00, :15, :30, :45) | Reset Trigger | Status |
|---|---|---|---|
| **15m Bar Quote Volume** | Reset to `$0.000M` | `now_cts != current_candle_ts` | ✅ **PASS (Zero-Reset)** |
| **15m Base Volume (BTC)** | Reset to `0.00 BTC` | `now_cts != current_candle_ts` | ✅ **PASS (Zero-Reset)** |
| **Footprint Ladder Bins** | Clear all $25 price buckets | `profile.clear()` on candle ts mismatch | ✅ **PASS (Zero-Reset)** |
| **Footprint Net Delta** | Reset to `+0.0000 BTC` | Sub-millisecond tick aggregation | ✅ **PASS (Zero-Reset)** |
| **Taker Buy / Sell Count** | Reset to `0 / 0` trades | Candle trade count rollover | ✅ **PASS (Zero-Reset)** |
| **Forced Liquidations** | Reset to `$0.00 / $0.00` | 15m bar liquidation accumulator reset | ✅ **PASS (Zero-Reset)** |
| **Session Futures CVD** | **PRESERVE ACCUMULATOR** | Continuous running sum across bars | ✅ **PASS (Preserved)** |
| **Session Spot CVD** | **PRESERVE ACCUMULATOR** | Continuous running sum across bars | ✅ **PASS (Preserved)** |
| **EMAs (8/21/50/200/800)** | **PRESERVE CONTINUITY** | Recursive EMA smoothing across bars | ✅ **PASS (Preserved)** |
| **ATRs (14/100)** | **PRESERVE CONTINUITY** | Wilder RMA continuous true range | ✅ **PASS (Preserved)** |
| **Open Interest & Funding** | **PRESERVE VALUE** | Real-time market state | ✅ **PASS (Preserved)** |
| **Order Book Depth (±1%)** | **PRESERVE REST CACHE** | 1.5s REST depth polling cache | ✅ **PASS (Preserved)** |

---

## 2. Master Parity Excel Spreadsheet Exported
The comprehensive comparison across all 28 indicators, footprint levels, gate audits, and lifecycle rules is exported to:
- Workspace: `c:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR\CoinGlass_vs_Binance_Parity_Master.xlsx`
- Artifact: `file:///C:/Users/SIGMA/.gemini/antigravity-ide/brain/26d6ef1f-8af0-428f-a6a1-5e5749a3efdc/CoinGlass_vs_Binance_Parity_Master.xlsx`

### Workbook Sheets:
1. **`Master_Parity_Comparison`**: Full 28-indicator comparison with raw formulas, deltas, and venue scope tags.
2. **`Footprint_Ladder_Profile`**: Bucket-by-bucket volume, delta, and POC breakdown.
3. **`Verification_Gates_Audit`**: Multi-Gate (Gate 1 through Gate 4) audit trail with evidence.
4. **`Rollover_Lifecycle_Spec`**: Detailed boundary reset behavior specifications.

---

## 3. Gate 4 Verdict
**Gate 4 is officially PASSED and verified.**
