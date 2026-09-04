# 🛡️ SYSTEM & QUANTITATIVE INVARIANTS

> **MANDATORY SYSTEM-WIDE INVARIANTS & UNBREAKABLE RULES**
> These invariants are verified, immutable, and must be respected by all agents and scripts.

---

## 1. Project Conventions & Git Workflow
- **Git Branching**: Always create a dedicated branch for major code changes (`feature/[task-slug]` or `fix/[bug-slug]`).
- **Minimal Files Policy**: Never generate fragmented, single-use, or redundant duplicate scripts. Consolidate related tasks into unified entrypoints.
- **Dual `.agents` Parity**: Every edit to rules, memory, or scripts must be mirrored 1:1 between `Engine_1_arena_PR/.agents` and `Engine_2/.agents`.

---

## 2. CoinGlass Scraper Authentication & Layout Invariant

### ⛔ CRITICAL INVARIANT: DO NOT MODIFY OR REFACTOR THIS FLOW
The CoinGlass UI authentication, layout loading, and 15-minute timeframe enforcement sequence is **100% verified and immutable**.

### Flow Specification:
1. **Authentication Check & Login Submission**:
   - URL: `https://www.coinglass.com/login`
   - Email Selector: `page.get_by_role("textbox", name="Email")` $\to$ `singhkaranbir0248@gmail.com`
   - Password Selector: `page.get_by_role("textbox", name="Password")` $\to$ `Lu$er2hero`
   - Submit Button: `page.get_by_role("button", name="Login").nth(1)`
2. **S9 Layout Loading**:
   - URL: `https://www.coinglass.com/tv/layout/s9`
   - Login page is closed upon navigation to S9.
3. **L_1 Preset Activation**:
   - Layout menu button: `page.get_by_role("button").filter(has_text=re.compile(r"^$")).nth(3)`
   - Load Chart Layout menu item: `page.get_by_role("menuitem", name="Load Chart Layout")`
   - Preset button: `page.get_by_role("button", name="L_1")`
4. **15m Timeframe Enforcement (All 9 Cells)**:
   - Click cell canvas / frame to focus (`canvas.nth(1).click(position={"x": 280, "y": 90})`)
   - Click interval dropdown (`page.get_by_role("button").filter(has_text=re.compile(r"^$")).nth(2)`)
   - Click `15m` button (`page.get_by_text("15m")`)
5. **Target Symbol Assignment (All 9 Cells)**:
   - Click cell canvas / frame (`canvas.nth(1).click(position={"x": 300, "y": 80})`)
   - Click symbol button (`page.get_by_role("button").first`)
   - Fill `#tv-ss` input with symbol (`locator("#tv-ss").fill(symbol)`)
   - Click matching result item or press `Enter`

### Affected Implementation Files:
- `Engine_1.py`
- `coinglass_scraper.py`
- `engine_components/coinglass_scraper.py`
- `tools/execute_perfect_coinglass_setup.py`

*Rule for all agents:* Do NOT edit button indices, dropdown locators, or navigation order in this sequence.

---

## 3. Quantitative Strategy & Microstructure Best Practices

### A. Overcoming Execution Friction (Fee Bleed)
- **The Problem**: 0.10% roundtrip taker fees and slippage (23 bps total drag) drain high-frequency strategies if trade margins are too thin.
- **Invariant**: Always enforce a minimum distance threshold (`dist_pct > 0.0035` or 0.35%) from the mean reversion target (like VWAP). Never take trades that are too close to the mean.
- **Filter Synergy**: Combine statistical bands (Z-score > 1.8 or VWAP 2.2 SD) with momentum exhaustion (RSI < 40 or RSI > 70) and CVD divergence ($\Delta\text{Spot} > 0 \land \Delta\text{Futures} < 0$).

### B. Microstructure Exit Ratchet vs. Static ATR
- **The Problem**: Static ATR trailing stops or frozen 5.0R targets retrace 85.8% of winning trades into stop-outs on 15m crypto.
- **Invariant Ratchet**:
  - **Phase 0 Breakeven Ratchet**: At $+0.8\text{R}$ gain, move stop to entry $+0.15\text{R}$ (covers fees).
  - **Phase 1 Profit Lock**: At $+1.5\text{R}$ gain, move stop to entry $+0.80\text{R}$.
  - **Target**: $+2.5\text{R}$ exit.
  - **Time Decay**: Exit at market if trade fails to gain $+0.2\text{R}$ within 24 bars (6 hours).

### C. System Memory Constraints & ML Stability
- **The Problem**: Running multi-threaded Optuna alongside parallel ML models (`n_jobs=-1`) across 18 symbols causes Out-Of-Memory (OOM) access violations.
- **Best Practice**:
  1. Strict garbage collection: Never hold raw candle DataFrames in memory once feature matrices are computed.
  2. Smart checkpointing: Persist window results incrementally (`oos_cache_{strategy}.json`) at the end of each window.

### D. Zero-Lookahead OOS Rigor
- **The Problem**: In-run OOS search and lookup tables lead to catastrophic out-of-sample failure.
- **Invariant**: Strictly causal execution. All hyperparameters, thresholds ($p^*$), and sizing decisions must be derived strictly on in-sample data prior to the test window ($t_{\text{purge}} = t_{\text{start}} - 72\text{h}$).
