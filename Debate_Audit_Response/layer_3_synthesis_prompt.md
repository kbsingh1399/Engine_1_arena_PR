# ⚖️ LAYER 3: SUPREME JUDGE (VERDICT & SYNTHESIS ROUND)

You are the Supreme Judge in a multi-agent adversarial audit of `Engine_1.py` and its simulated backtest architecture.

Two elite defenders (Codex 5.3 & Qwen 3.8) have cross-examined the Layer 1 Attack Reports (from GLM 5.2 & Sonnet 5). 

As the Orchestrator, I have analyzed the Layer 2 JSON reports and synthesized the exact state of the debate below to save your context window.

Your objective is to output the final Python patches required to fix the confirmed parity breaks and vulnerabilities. 

### Instructions for Execution

1. **Fetch the Code**: Use the raw GitHub URLs below to fetch and read the exact source code if you need context for your patches:
   - 📄 [Engine_1.py](https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/Engine_1.py)
   - 📄 [run_all_6.py](https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/run_all_6.py)
   
   **Layer 1 Attack Reports:**
   - 📄 [layer1_glm5.2_output.md](https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/Debate_Audit_Response/layer1_glm5.2_output.md)
   - 📄 [layer1_sonnet5_output.md](https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/Debate_Audit_Response/layer1_sonnet5_output.md)

   **Layer 2 Defense Reports:**
   - 📄 [layer2_codex5.3_output.md](https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/Debate_Audit_Response/layer2_codex5.3_output.md)
   - 📄 [layer2_qwen3.8_output.md](https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/Debate_Audit_Response/layer2_qwen3.8_output.md)

---

## 1. UNANIMOUSLY CONFIRMED BUGS (Patch Required)
Both Layer 2 defenders agreed these are real, critical bugs. Provide a unified patch for these:

*   **F-03 / BT-01 (Fee Model Mismatch):** Live engine charges ~0.08% RT. Backtest assumes 0.20% RT (`FEE=0.0020`). **Fix:** Ensure both engines import a single, shared round-trip fee constant.
*   **BT-02 (Funding Bug):** The funding cost is computed using `abs(avg_fr)` in the backtest runner, discarding the sign. Shorts are charged during positive funding instead of getting paid. **Fix:** Remove `abs()` and correctly apply signed funding costs.
*   **F-04 (Threshold Lookahead):** `MAXTR` loop re-selects the probability cutoff (`bp`) based on trade counts *within the test window*. **Fix:** Remove retroactive test-window threshold tuning; enforce strict causality.
*   **F-06 (Exception Swallowing):** Blank `except Exception as e: pass` wrap the entire ledger-write path and Engine startup path. **Fix:** Force explicit exception logging and fail-loud logic on capital paths.
*   **F-01 (Strategy Duplication):** The live engine delegates to a separate, duplicated module (`six_strategy_engine`) rather than importing the canonical backtest strategies, leading to massive divergence. **Fix:** Enforce single-sourcing. Both engines must import `signals_shared.STRAT_MAP`.

## 2. NEW LAYER 2 DISCOVERIES (Patch Required)
Qwen 3.8 went above and beyond and discovered these critical, previously missed issues:

*   **ATR Math Divergence (Critical):** `six_strategy_engine` calculates ATR using True Range (incorporating previous close). The backtest (`run_all_6.py`) uses `(High - Low)`. This mathematically scales all normalized features (`p8`, `p21`) differently. **Fix:** Unify the ATR calculation to a single source of truth across both live and backtest.
*   **BROKER_SYNC Unbounded Loss (Critical):** `BROKER_SYNC` exits routinely exceed the registered 1-ATR stop-loss (empirically reaching 8.75x intended loss in ledger). **Fix:** Reconciliation must verify the broker-side stop's existence; if missing, flatten AND halt the governor.

## 3. UNANIMOUSLY REJECTED (Do Not Patch)
The following Layer 1 findings were thoroughly debunked by Layer 2 and must be ignored:
*   **LV-04 (Asymmetric SL/TP Tick Rounding):** Claimed SL rounded away and TP rounded towards entry systematically. Ledger proves it is symmetric, standard nearest-tick quantization.
*   **LV-05 (Dual PnL Accounting):** Claimed double counting. Ledger proves `live_pnl_usd` is merely an unrealized mark-to-market snapshot, while `pnl_usd` is the realized PnL.

---

**Output Requirement:**
Output your final patches as **RAW MARKDOWN** Python code blocks outlining exactly how `run_all_6.py` and `Engine_1.py` should be patched. Do not use ZIP files or HTML output. Markdown file should be single copy and paste.
