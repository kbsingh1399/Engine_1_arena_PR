# WF20 Ensemble Walk-Forward Report — S1_Liquidation (multi-concept universe)

- Generated: 2026-08-27 16:14:02.600755
- **Final status: HALTED at window 1 after 4 re-optimization rounds — gates not met**
- Capital $5000/acct, 1R=$35, fees+slip 0.08% RT, max 2 concurrent positions
- Gates: ROI > 20.0%, MaxDD < 5.0%, WR > 40.0%, 6-100 trades
- Universe: 17 causal concepts pooled (see wf20_screen.py)
- Ensemble: LightGBM + XGBoost + CatBoost + HistGBM (mean-vote, isotonic-calibrated)

| # | Window | Trades | WR % | ROI % | MaxDD % | PnL $ | Pass |
|---|--------|--------|------|-------|---------|-------|------|
| 1 | 2021-01-01 → 2021-03-31 | 100 | 40.0 | -12.82 | 21.67 | -641.11 | FAIL |

## Final parameters
```json
{
  "p_long": 0.4602349601427465,
  "p_short": 0.5499815671831061,
  "skip_chop": 1,
  "lgbm_depth": 3,
  "lgbm_lr": 0.03538700248743959,
  "xgb_depth": 5,
  "xgb_lr": 0.07183699591992246,
  "cat_lr": 0.026454769751878812,
  "hgb_lr": 0.01680302420770403
}
```
