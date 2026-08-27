# WF20 Autonomous Walk-Forward Report — S1_Liquidation

- Generated: 2026-08-27 15:57:27.567795
- **Final status: HALTED at window 1 after 4 re-optimization rounds — gates not met**
- Capital $5000/acct, 1R=$35, fees+slip 0.08% RT, max 2 concurrent positions
- Gates: ROI > 20.0%, MaxDD < 5.0%, WR > 40.0%, 6-100 trades

| # | Window | Trades | WR % | ROI % | MaxDD % | PnL $ | Pass |
|---|--------|--------|------|-------|---------|-------|------|
| 1 | 2021-01-01 → 2021-03-31 | 83 | 49.4 | 0.16 | 9.65 | 8.0 | FAIL |

## Final parameters
```json
{
  "pullback_threshold": 0.3220760298445636,
  "liq_mult": 1.5053628130673387,
  "zc_gate": 0.2706137984411567,
  "q1": 0.5376283432638637,
  "p_long": 0.4713603670192249,
  "p_short": 0.7867650119564664,
  "skip_chop": 0,
  "lgbm_depth": 3,
  "lgbm_lr": 0.01739732933787523,
  "xgb_depth": 3,
  "xgb_lr": 0.045621775411467315
}
```
