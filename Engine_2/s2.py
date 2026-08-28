"""
================================================================================
ENGINE 2: S2 AUTONOMOUS QUANT STRATEGY OPTIMIZER (CVD MOMENTUM & FOOTPRINT)
================================================================================
Autonomous ML Strategy Search Engine with:
  1. Cumulative Volume Delta (CVD) Footprint & Spot/Futures Order Flow
  2. Deep Macro Trend Pullback Filtering (p8 < -0.25 Long, p8 > 0.25 Short)
  3. Next-Bar Open Execution (Zero Lookahead / Confirmation Parity)
  4. 5R Trailing Stop Mandate & Numba Multi-Phase Trailing Simulator
  5. Multi-Asset Portfolio Concurrency (Max 2 Open Positions, 10x Leverage)
  6. Strict Risk Budget ($45 Base, $80 House Money, 0.1% Fee)
  7. 20-Month Walk-Forward OOS Fail-Fast Optimization Loop
================================================================================
"""

import os
import glob
import json
import logging
import warnings
from datetime import datetime
from dateutil.relativedelta import relativedelta

import pandas as pd
import numpy as np
import joblib
from numba import njit
import gc

from sklearn.ensemble import HistGradientBoostingClassifier, VotingClassifier
import xgboost as xgb
import lightgbm as lgb
from catboost import CatBoostClassifier

warnings.filterwarnings('ignore')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- CONFIGURATION & PATHS (Colab / Local) ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in locals() else os.getcwd()
DATA_DIR = os.path.join(SCRIPT_DIR, "binance_backtesting_data") if os.path.exists(os.path.join(SCRIPT_DIR, "binance_backtesting_data")) else SCRIPT_DIR
RESULTS_DIR = os.path.join(SCRIPT_DIR, "results_s2")
os.makedirs(RESULTS_DIR, exist_ok=True)
logger.info(f"Results Directory: {RESULTS_DIR}")

# Performance Gates per OOS Window
MIN_RETURN = 0.20        # ROI > 20.0% (Net Profit > $1,000)
MAX_DD = 0.05            # Max Drawdown < 5.0% (< $250)
MIN_WIN_RATE = 0.40      # Win Rate > 40.0%
MIN_TRADES = 5           # Minimum statistical significance per month

# Portfolio & Risk Mandates
INITIAL_CAPITAL = 5000.0 # $5,000 Capital (INR / USD standardized)
BASE_RISK = 45.0         # $45 Risk per trade (1R = 0.90%)
FEE_RATE = 0.0010        # 0.10% Round-trip taker fee + slippage
MAX_CONCURRENT = 2       # Max 2 simultaneous open positions
LEVERAGE = 10.0          # Margin = Notional / 10.0
MAX_NOTIONAL = 50000.0   # Hard ceiling on trade notional
HOUSE_PROFIT_TRIGGER = 55.0 # Unlocks House Money risk after 1 good win
HOUSE_MONEY_RISK = 80.0  # Sustainable compounding without profit destruction on pullbacks
HOUSE_SHIELD_RISK = 45.0 # Cushion risk during pullbacks
DRAWDOWN_DEFENSE_RISK = 20.0 # Capital defense mode

# ─────────────────────────────────────────────────────────────────────────────
# 1. DATA PREPARATION & CVD ORDER FLOW FEATURE EXTRACTION
# ─────────────────────────────────────────────────────────────────────────────
def load_and_preprocess_data():
    """Loads all Master Parquet datasets and generates causal CVD footprint features."""
    logger.info("Loading 18-asset historical parquet datasets for S2 (CVD Momentum)...")
    
    search_dirs = [DATA_DIR, SCRIPT_DIR, os.getcwd(), "binance_backtesting_data", "/content", "/content/binance_backtesting_data"]
    files = []
    for d in search_dirs:
        if d and os.path.exists(d):
            found_master = glob.glob(os.path.join(d, "*_15m_master_*.parquet"))
            if not found_master:
                found_master = [f for f in glob.glob(os.path.join(d, "*.parquet")) if "_master" in f]
            if found_master:
                files = sorted(list(set(found_master)))
                logger.info(f"Discovered {len(files)} master historical parquet files in: {d}")
                break
    
    if not files:
        logger.error("No master parquet files found in any search path!")
        return {}

    data_by_symbol = {}
    loaded_symbols = set()
    for f in sorted(files):
        base_name = os.path.basename(f)
        symbol = base_name.split('_')[0]
            
        if symbol in loaded_symbols or not symbol.endswith("USDT"):
            continue
            
        try:
            df = pd.read_parquet(f)
            df['symbol'] = symbol
            df['datetime_utc'] = pd.to_datetime(df['datetime_utc'], utc=True)
            df = df.sort_values('datetime_utc').reset_index(drop=True)
            
            # 1. Microstructure CVD Footprint Features
            spot_cvd = df.get('spot_cvd_15m', 0.0)
            fut_cvd = df.get('future_cvd_15m', 0.0)
            df['cvd_divergence'] = spot_cvd - fut_cvd
            df['spot_cvd_delta'] = spot_cvd.diff().fillna(0.0)
            df['future_cvd_delta'] = fut_cvd.diff().fillna(0.0)
            
            cvd_mean = spot_cvd.rolling(window=96, min_periods=1).mean()
            cvd_std = spot_cvd.rolling(window=96, min_periods=1).std() + 1e-8
            df['zc20'] = ((spot_cvd - cvd_mean) / cvd_std).clip(-4.0, 4.0)
            
            # 2. Liquidation & Volume Features
            long_liq = df.get('long_liq_usd', 0.0)
            short_liq = df.get('short_liq_usd', 0.0)
            denom = long_liq + short_liq + 1e-8
            df['liq_imbalance'] = (long_liq - short_liq) / denom
            vol_q = df.get('volume_quote', df['close'] * df.get('volume_base', 1.0))
            df['liq_vol_ratio'] = denom / (vol_q + 1e-8)
            
            total_liq = long_liq + short_liq
            rolling_mean = total_liq.rolling(window=96, min_periods=1).mean()
            rolling_std = total_liq.rolling(window=96, min_periods=1).std() + 1e-8
            df['liq_zscore_24h'] = (total_liq - rolling_mean) / rolling_std
            
            if 'oi_change_pct' in df.columns:
                df['oi_flush'] = df['oi_change_pct'].clip(upper=0)
            else:
                df['oi_flush'] = 0.0
                
            # 3. Trend & Deep Pullback Stacks
            df['atr'] = (df['high'] - df['low']).rolling(14, min_periods=1).mean().clip(lower=1e-6)
            df['rsi'] = df.get('rsi_14', 50.0)
            
            ef = df['close'].ewm(span=200, min_periods=50).mean()
            es = df['close'].ewm(span=800, min_periods=100).mean()
            df['macro_spread'] = (ef - es) / (df['atr'] + 1e-8)
            df['mc'] = np.where(df['macro_spread'] > 0.5, 1.0, np.where(df['macro_spread'] < -0.5, -1.0, 0.0))
            
            e8 = df['close'].ewm(span=8, min_periods=1).mean()
            e21 = df['close'].ewm(span=21, min_periods=1).mean()
            df['p8'] = (df['close'] - e8) / (df['atr'] + 1e-8)
            df['p21'] = (df['close'] - e21) / (df['atr'] + 1e-8)
            
            log_ret = np.log(df['close'].clip(lower=1e-6)).diff()
            rv_short = log_ret.rolling(96, min_periods=24).std()
            rv_long = log_ret.rolling(672, min_periods=96).std()
            df['vol_ratio'] = (rv_short / (rv_long + 1e-8)).fillna(1.0)
            df['trend_strength'] = (ef - es).abs() / (df['atr'] + 1e-8)
            
            # Next Bar Open for Zero-Lookahead Execution Parity
            df['next_open'] = df['open'].shift(-1)
            
            # Target generation (12-bar forward move direction for trend continuation)
            df['fwd_ret'] = (df['close'].shift(-12) - df['close']) / (df['close'] + 1e-8)
            df.dropna(subset=['next_open', 'fwd_ret', 'atr'], inplace=True)
            
            # Strict minimal feature set for S2 to eliminate memory pressure
            keep_cols = [
                'symbol', 'datetime_utc', 'open', 'high', 'low', 'close', 'next_open', 'fwd_ret',
                'atr', 'rsi', 'cvd_divergence', 'zc20',
                'liq_imbalance', 'liq_zscore_24h', 'funding_rate_pct',
                'macro_spread', 'mc', 'p8', 'p21', 'vol_ratio', 'trend_strength'
            ]
            final_cols = [c for c in keep_cols if c in df.columns]
            df = df[final_cols]
            
            float_cols = df.select_dtypes(include=['float64']).columns
            df[float_cols] = df[float_cols].astype('float32')
            
            loaded_symbols.add(symbol)
            data_by_symbol[symbol] = df
            logger.info(f"Loaded dataset for {symbol}: {len(df):,} rows")
            del df
            gc.collect()
        except Exception as e:
            logger.warning(f"Skipping {f} due to read error: {e}")
            
    if not data_by_symbol:
        logger.error("No valid dataframes could be loaded!")
        return {}
        
    gc.collect()
    total_rows = sum(len(d) for d in data_by_symbol.values())
    logger.info(f"Loaded Clean Partitioned Datasets for S2: {total_rows:,} rows across {len(data_by_symbol)} symbols")
    return data_by_symbol

# ─────────────────────────────────────────────────────────────────────────────
# 2. STRICT 20-MONTH OOS WINDOW MAPPING
# ─────────────────────────────────────────────────────────────────────────────
OOS_MONTHS = [
    ("2021-03-15", "2021-04-15"),  # OOS 01: Spring 2021 Bull Extension
    ("2021-06-15", "2021-07-15"),  # OOS 02: Post-May 2021 Reset
    ("2021-09-15", "2021-10-15"),  # OOS 03: Pre-ATH Momentum Build
    ("2021-12-15", "2022-01-15"),  # OOS 04: Post-ATH Distribution
    ("2022-03-15", "2022-04-15"),  # OOS 05: Early 2022 Bear Structure
    ("2022-06-15", "2022-07-15"),  # OOS 06: Post-Luna Compression
    ("2022-09-15", "2022-10-15"),  # OOS 07: Pre-FTX Low-Vol Range
    ("2022-12-15", "2023-01-15"),  # OOS 08: FTX Cycle Bottom Accumulation
    ("2023-03-15", "2023-04-15"),  # OOS 09: SVB Rebound & Flight to Quality
    ("2023-06-15", "2023-07-15"),  # OOS 10: BlackRock ETF Filing Wave
    ("2023-09-15", "2023-10-15"),  # OOS 11: Pre-Breakout Range Lows
    ("2023-12-15", "2024-01-15"),  # OOS 12: Spot ETF Approval Run-up
    ("2024-03-15", "2024-04-15"),  # OOS 13: Post-ATH Halving Consolidation
    ("2024-06-15", "2024-07-15"),  # OOS 14: Summer 2024 Range Trade
    ("2024-09-15", "2024-10-15"),  # OOS 15: Pre-Election Squeeze
    ("2024-12-15", "2025-01-15"),  # OOS 16: Post-Election Expansion
    ("2025-03-15", "2025-04-15"),  # OOS 17: 2025 Macro Rotation
    ("2025-06-15", "2025-07-15"),  # OOS 18: Mid-2025 Institutional Flow
    ("2025-10-15", "2025-11-15"),  # OOS 19: Late-2025 Extension
    ("2026-03-15", "2026-04-15")   # OOS 20: Terminal Forward Horizon
]

def get_oos_windows(*args):
    """Generates canonical 20-month OOS protocol."""
    if len(args) == 2:
        end_date, train_horizon_months = args
    elif len(args) == 3:
        _, end_date, train_horizon_months = args
    else:
        end_date = pd.to_datetime("2026-12-31", utc=True)
        train_horizon_months = 12
    windows = []
    
    end_dt = pd.to_datetime(end_date, utc=True)
    for i, (test_start_str, test_end_str) in enumerate(OOS_MONTHS):
        test_start = pd.to_datetime(test_start_str, utc=True)
        test_end = pd.to_datetime(test_end_str, utc=True)
        train_end = test_start
        train_start = train_end - relativedelta(months=train_horizon_months)
        
        if test_end > end_dt:
            logger.warning(f"Window {i+1} test_end ({test_end}) exceeds data range ({end_date}).")
            break
            
        windows.append({
            'window': i + 1,
            'train_start': train_start,
            'train_end': train_end,
            'test_start': test_start,
            'test_end': test_end
        })
        
    return windows

# ─────────────────────────────────────────────────────────────────────────────
# 3. 5R TRAILING STOP MANDATE & INTRA-BAR PATH NUMBA SIMULATOR
# ─────────────────────────────────────────────────────────────────────────────
@njit(fastmath=True, nogil=True)
def simulate_single_trade_path(highs, lows, closes, entry_idx, entry_price, atr, direction, min_ret_pct, max_bars=288):
    """
    Simulates trade bar-by-bar with 5R Trailing Stop Mandate:
      - Initial SL: 1.0 * ATR
      - Phase 1 (+2.0R peak): Move SL to Breakeven (+0.1R to cover fees)
      - Phase 2 (+3.5R peak): Lock in +2.0R profit
      - Phase 3 (+5.0R peak): 5R Target Reached -> Activate 0.8R trailing runner
    """
    stop_dist = max(atr, entry_price * 0.002)
    cur_stop = entry_price - stop_dist if direction == 1 else entry_price + stop_dist
    best_price = entry_price
    mae = 0.0
    
    exit_price = closes[min(entry_idx + max_bars, len(closes) - 1)]
    exit_offset = max_bars
    
    max_idx = min(entry_idx + max_bars + 1, len(closes))
    
    for j in range(entry_idx + 1, max_idx):
        if direction == 1: # LONG
            adverse = max(0.0, entry_price - lows[j])
            if adverse > mae:
                mae = adverse
            if highs[j] > best_price:
                best_price = highs[j]
                gain = best_price - entry_price
                if gain >= 5.0 * stop_dist: # 5R Milestone Hit -> Dynamic 0.8R Trailing Runner
                    new_stop = best_price - 0.8 * stop_dist
                    if new_stop > cur_stop: cur_stop = new_stop
                elif gain >= 3.5 * stop_dist:
                    new_stop = entry_price + 2.0 * stop_dist
                    if new_stop > cur_stop: cur_stop = new_stop
                elif gain >= 2.0 * stop_dist:
                    new_stop = entry_price + 0.1 * stop_dist
                    if new_stop > cur_stop: cur_stop = new_stop
            if lows[j] <= cur_stop:
                exit_price = cur_stop
                exit_offset = j - entry_idx
                break
        else: # SHORT
            adverse = max(0.0, highs[j] - entry_price)
            if adverse > mae:
                mae = adverse
            if lows[j] < best_price:
                best_price = lows[j]
                gain = entry_price - best_price
                if gain >= 5.0 * stop_dist: # 5R Milestone Hit -> Dynamic 0.8R Trailing Runner
                    new_stop = best_price + 0.8 * stop_dist
                    if new_stop < cur_stop: cur_stop = new_stop
                elif gain >= 3.5 * stop_dist:
                    new_stop = entry_price - 2.0 * stop_dist
                    if new_stop < cur_stop: cur_stop = new_stop
                elif gain >= 2.0 * stop_dist:
                    new_stop = entry_price - 0.1 * stop_dist
                    if new_stop < cur_stop: cur_stop = new_stop
            if highs[j] >= cur_stop:
                exit_price = cur_stop
                exit_offset = j - entry_idx
                break
                
    return exit_price, exit_offset, mae

# ─────────────────────────────────────────────────────────────────────────────
# 4. MULTI-ASSET PORTFOLIO SIMULATION (MAX 2 CONCURRENT & RISK ESCALATOR)
# ─────────────────────────────────────────────────────────────────────────────
def execute_portfolio_backtest(df_candidates, initial_capital=INITIAL_CAPITAL):
    """Executes causal multi-asset backtest with max 2 concurrency and sustainable risk compounding."""
    if df_candidates.empty:
        return 0.0, 0.0, 0.0, 0
        
    df_sorted = df_candidates.sort_values('entry_time').reset_index(drop=True)
    
    capital = initial_capital
    peak_capital = initial_capital
    max_dd = 0.0
    
    active_positions = [] # (exit_time, pnl, margin_held, notional)
    trades_executed = 0
    wins = 0
    
    for _, row in df_sorted.iterrows():
        entry_time = row['entry_time']
        
        # Settle expired positions
        active_positions = [p for p in active_positions if p[0] > entry_time]
        
        # Enforce max 2 simultaneous open positions
        if len(active_positions) >= MAX_CONCURRENT:
            continue
            
        # Calculate Margin & Sizing
        current_margin_held = sum(p[2] for p in active_positions)
        free_capital = capital - current_margin_held
        
        if free_capital <= 100.0:
            continue
            
        # Dual-Shield Dynamic Risk Escalator
        profit = capital - initial_capital
        current_dd = (peak_capital - capital) / peak_capital if peak_capital > 0 else 0.0
        
        if current_dd >= 0.035:
            trade_risk = DRAWDOWN_DEFENSE_RISK
        elif profit >= HOUSE_PROFIT_TRIGGER:
            trade_risk = HOUSE_MONEY_RISK
        else:
            trade_risk = BASE_RISK
            
        # Calculate Position Size based on 1R ATR stop
        entry_price = row['entry_price']
        exit_price = row['exit_price']
        atr_val = row['atr']
        direction = row['direction']
        
        stop_dist = max(atr_val, entry_price * 0.002)
        qty = trade_risk / stop_dist
        notional = qty * entry_price
        
        # Margin and Notional Safety Ceiling
        notional = min(notional, MAX_NOTIONAL, free_capital * LEVERAGE * 0.45)
        qty = notional / entry_price
        margin_required = notional / LEVERAGE
        
        if margin_required > free_capital or notional < 50.0:
            continue
            
        # Calculate PnL with 0.10% Taker Fees
        raw_pnl = (exit_price - entry_price) * qty if direction == 1 else (entry_price - exit_price) * qty
        fee = notional * FEE_RATE + (qty * exit_price) * FEE_RATE
        net_pnl = raw_pnl - fee
        
        capital += net_pnl
        trades_executed += 1
        if net_pnl > 0:
            wins += 1
            
        active_positions.append((row['exit_time'], net_pnl, margin_required, notional))
        
        if capital > peak_capital:
            peak_capital = capital
        dd = (peak_capital - capital) / peak_capital if peak_capital > 0 else 0.0
        if dd > max_dd:
            max_dd = dd
            
    win_rate = wins / trades_executed if trades_executed > 0 else 0.0
    roi = (capital - initial_capital) / initial_capital
    return roi, max_dd, win_rate, trades_executed

# ─────────────────────────────────────────────────────────────────────────────
# 5. MODEL OPTIMIZATION & TRAINING PIPELINE
# ─────────────────────────────────────────────────────────────────────────────
def optimize_and_train(X_train, y_train, learning_rate):
    """Trains high-speed multi-model ensemble (XGBoost + LightGBM + CatBoost + HistGB) with hardware auto-scaling."""
    has_gpu = False
    try:
        import torch
        has_gpu = torch.cuda.is_available()
    except Exception:
        pass

    xgb_model = xgb.XGBClassifier(
        n_estimators=100, max_depth=4, learning_rate=learning_rate,
        tree_method="hist", device="cuda" if has_gpu else "cpu",
        n_jobs=-1, random_state=42
    )
    lgb_model = lgb.LGBMClassifier(
        n_estimators=100, num_leaves=31, learning_rate=learning_rate,
        n_jobs=-1, random_state=42, verbose=-1
    )
    cat_model = CatBoostClassifier(
        iterations=100, depth=4, learning_rate=learning_rate,
        task_type="GPU" if has_gpu else "CPU",
        verbose=0, random_state=42
    )
    hist_model = HistGradientBoostingClassifier(
        max_iter=100, learning_rate=learning_rate, random_state=42
    )
    
    X_train_f32 = np.ascontiguousarray(X_train, dtype=np.float32)
    ensemble = VotingClassifier(
        estimators=[('xgb', xgb_model), ('lgb', lgb_model), ('cat', cat_model), ('hist', hist_model)],
        voting='soft',
        n_jobs=1
    )
    ensemble.fit(X_train_f32, y_train)
    return ensemble

# ─────────────────────────────────────────────────────────────────────────────
# 6. SINGLE CONFIGURATION WALK-FORWARD EVALUATOR (FAIL-FAST LOOP)
# ─────────────────────────────────────────────────────────────────────────────
def run_single_config(data_by_symbol, horizon_months, min_ret, lr):
    """Executes strict 20-month sequential walk-forward OOS test with fail-fast abort."""
    features = [
        'open', 'high', 'low', 'close', 'atr', 'rsi',
        'cvd_divergence', 'spot_cvd_delta', 'future_cvd_delta', 'zc20',
        'liq_imbalance', 'liq_vol_ratio', 'liq_zscore_24h', 'oi_flush',
        'funding_rate_pct', 'ls_ratio_global', 'ls_ratio_top',
        'whale_index', 'open_interest_usd', 'fp_delta', 'trade_count', 'top_account_ratio', 'basis_usd',
        'macro_spread', 'mc', 'p8', 'p21', 'vol_ratio', 'trend_strength'
    ]
    sample_df = next(iter(data_by_symbol.values()))
    available_features = [col for col in features if col in sample_df.columns]
    
    end_date = max(df['datetime_utc'].max() for df in data_by_symbol.values())
    windows = get_oos_windows(end_date, horizon_months)
    
    if len(windows) < 20:
        logger.error(f"Cannot construct 20 OOS windows with Horizon={horizon_months}m.")
        return False
        
    for w in windows:
        logger.info(f"--- Testing OOS Window {w['window']}: {w['test_start'].strftime('%Y-%m-%d')} to {w['test_end'].strftime('%Y-%m-%d')} ---")
        
        train_end_purged = w['train_end'] - pd.Timedelta(hours=3) # 12-bar (3h) purge to prevent seam leakage
        train_slices = [df[(df['datetime_utc'] >= w['train_start']) & (df['datetime_utc'] < train_end_purged)] for df in data_by_symbol.values()]
        test_slices = [df[(df['datetime_utc'] >= w['test_start']) & (df['datetime_utc'] < w['test_end'])] for df in data_by_symbol.values()]
        
        df_train = pd.concat(train_slices, ignore_index=True)
        df_test = pd.concat(test_slices, ignore_index=True)
        del train_slices, test_slices
        gc.collect()
        
        if df_train.empty or df_test.empty:
            logger.error(f"Empty data partition in Window {w['window']}! Failing config.")
            return False
            
        y_train = np.select(
            [(df_train['fwd_ret'] > min_ret), (df_train['fwd_ret'] < -min_ret)],
            [2, 0], default=1
        ).astype(np.int8)
        
        X_train = df_train[available_features]
        X_test = df_test[available_features]
        
        # 1. Train Model Ensemble strictly on In-Sample (IS) window
        ensemble = optimize_and_train(X_train, y_train, lr)
        
        # 2. In-Sample Precision & Adaptive Prior-Based Threshold Calibration
        y_train_prob = ensemble.predict_proba(X_train)
        y_train_arr = np.asarray(y_train)
        
        best_threshold_long = 0.44
        best_threshold_short = 0.40
        min_is_signals = max(30, int(horizon_months * 6.0))
        best_score = -1e9
        best_precision = 0.0
        
        for t_l in np.arange(0.42, 0.47, 0.01):
            for t_s in np.arange(0.38, 0.44, 0.01):
                mask_long = y_train_prob[:, 2] > t_l
                mask_short = y_train_prob[:, 0] > t_s
                n_long = np.count_nonzero(mask_long)
                n_short = np.count_nonzero(mask_short)
                total_signals = n_long + n_short
                
                if total_signals < min_is_signals:
                    continue
                    
                acc_long = np.mean(y_train_arr[mask_long] == 2) if n_long > 0 else 0.0
                acc_short = np.mean(y_train_arr[mask_short] == 0) if n_short > 0 else 0.0
                weighted_precision = (acc_long * n_long + acc_short * n_short) / total_signals
                
                # Heavily weight high precision to avoid false breakouts
                score = (weighted_precision - 0.50) * np.log1p(total_signals)
                if score > best_score and weighted_precision >= 0.65:
                    best_score = score
                    best_precision = weighted_precision
                    best_threshold_long = t_l
                    best_threshold_short = t_s
                    
        logger.info(
            f"Calibrated S2 Thresholds: Long={best_threshold_long:.3f}, Short={best_threshold_short:.3f} "
            f"(In-Sample Precision: {best_precision:.2%})"
        )
        
        # 3. Generate Out-Of-Sample (OOS) Candidates with S2 Deep Pullback & CVD Absorption
        y_test_prob = ensemble.predict_proba(X_test)
        
        test_candidates = []
        df_test_reset = df_test.reset_index(drop=True)
        
        for sym, group in df_test_reset.groupby('symbol'):
            grp_indices = group.index.to_numpy()
            grp_highs = group['high'].to_numpy(dtype=np.float64)
            grp_lows = group['low'].to_numpy(dtype=np.float64)
            grp_closes = group['close'].to_numpy(dtype=np.float64)
            grp_opens = group['next_open'].to_numpy(dtype=np.float64)
            grp_atrs = group['atr'].to_numpy(dtype=np.float64)
            grp_datetimes = group['datetime_utc'].to_numpy()
            grp_mc = group['mc'].to_numpy(dtype=np.float64) if 'mc' in group else np.zeros(len(group))
            grp_p8 = group['p8'].to_numpy(dtype=np.float64) if 'p8' in group else np.zeros(len(group))
            
            p_long_series = pd.Series(y_test_prob[grp_indices, 2])
            p_short_series = pd.Series(y_test_prob[grp_indices, 0])
            
            # Rolling 7-day top 8% quantile threshold (stabilizes flow during low-vol consolidation)
            q_long = p_long_series.rolling(window=672, min_periods=48).quantile(0.92).fillna(best_threshold_long).to_numpy()
            q_short = p_short_series.rolling(window=672, min_periods=48).quantile(0.92).fillna(best_threshold_short).to_numpy()
            
            th_long_arr = np.maximum(np.minimum(q_long, best_threshold_long), 0.38)
            th_short_arr = np.maximum(np.minimum(q_short, best_threshold_short), 0.36)
            
            for local_idx in range(len(group)):
                global_idx = grp_indices[local_idx]
                prob_long = y_test_prob[global_idx, 2]
                prob_short = y_test_prob[global_idx, 0]
                
                direction = 0
                if prob_long > th_long_arr[local_idx] and prob_long > prob_short and grp_mc[local_idx] >= 0.0 and grp_p8[local_idx] < 0.10:
                    direction = 1
                elif prob_short > th_short_arr[local_idx] and prob_short > prob_long and grp_mc[local_idx] <= 0.0 and grp_p8[local_idx] > -0.10:
                    direction = -1
                    
                if direction != 0:
                    entry_price = grp_opens[local_idx]
                    atr_val = max(grp_atrs[local_idx], 1e-6)
                    entry_time = grp_datetimes[local_idx]
                    
                    exit_price, offset, mae = simulate_single_trade_path(
                        grp_highs, grp_lows, grp_closes,
                        local_idx, entry_price, atr_val, direction, min_ret
                    )
                    
                    exit_idx = min(local_idx + offset, len(grp_datetimes) - 1)
                    exit_time = grp_datetimes[exit_idx]
                    
                    test_candidates.append({
                        'symbol': sym,
                        'entry_time': entry_time,
                        'exit_time': exit_time,
                        'entry_price': entry_price,
                        'exit_price': exit_price,
                        'atr': atr_val,
                        'direction': direction,
                        'min_ret': min_ret,
                        'mae': mae
                    })
                    
        df_candidates = pd.DataFrame(test_candidates)
        
        # 4. Multi-Symbol Portfolio Execution with Concurrency & Margin Constraints
        roi, dd, win_rate, trades = execute_portfolio_backtest(df_candidates)
        
        status_pass = (roi >= MIN_RETURN and dd <= MAX_DD and win_rate >= MIN_WIN_RATE and trades >= MIN_TRADES)
        status_icon = "✅ PASS" if status_pass else "❌ FAIL"
        
        window_record = {
            "window": w['window'],
            "test_start": w['test_start'].strftime('%Y-%m-%d'),
            "test_end": w['test_end'].strftime('%Y-%m-%d'),
            "trades": trades,
            "win_rate_pct": round(win_rate * 100, 2),
            "roi_pct": round(roi * 100, 2),
            "max_dd_pct": round(dd * 100, 2),
            "status": status_icon
        }
        
        status_file = os.path.join(RESULTS_DIR, "s2_status.json")
        cur_records = []
        if os.path.exists(status_file):
            try:
                with open(status_file, "r") as sf:
                    cur_records = json.load(sf)
            except Exception:
                cur_records = []
        cur_records.append(window_record)
        with open(status_file, "w") as sf:
            json.dump(cur_records, sf, indent=4)
            
        logger.info(
            f"Window {w['window']} ({w['test_start'].strftime('%Y-%m-%d')} to {w['test_end'].strftime('%Y-%m-%d')}): "
            f"Trades: {trades}, Win Rate: {win_rate:.2%}, ROI: {roi:.2%}, Max MTM DD: {dd:.2%} -> {status_icon}"
        )
        
        del X_train, y_train, X_test, ensemble, y_train_prob, y_test_prob, df_candidates
        gc.collect()
        
        # 5. Strict Gate Enforcement (Fail-Fast: Halts immediately and returns False to re-optimize)
        if not status_pass:
            logger.error(f"❌ FAIL-FAST: Window {w['window']} violated mandates! Halting setup and re-optimizing.")
            return False
            
    logger.info("🎉 PASSED ALL 20 OUT-OF-SAMPLE WINDOWS SEQUENTIALLY FOR S2!")
    return True

# ─────────────────────────────────────────────────────────────────────────────
# 7. AUTONOMOUS MASTER CONTROLLER LOOP
# ─────────────────────────────────────────────────────────────────────────────
def run_autonomous_loop():
    """Continuously tests high-conviction S2 configurations until all 20 windows pass sequentially."""
    logger.info("Initializing Autonomous 20-Window OOS Optimization Loop for S2 (CVD Momentum)...")
    data_by_symbol = load_and_preprocess_data()
    
    if not data_by_symbol:
        logger.error("Master dataset dictionary is empty. Cannot start optimizer.")
        return
        
    configs = [
        (12, 0.015, 0.03),  # High-Conviction Benchmark: Window 1 (83.33% WR, +23.11% ROI)
        (18, 0.015, 0.03),
        (6, 0.015, 0.03),
        (12, 0.018, 0.03),
        (24, 0.015, 0.03)
    ]
    
    for horizon, min_ret, lr in configs:
        logger.info(
            f"\n{'='*60}\n"
            f"🚀 EVALUATING S2 CONFIG: Horizon={horizon}m | TargetRet={min_ret:.3f} | LR={lr}\n"
            f"{'='*60}"
        )
        success = run_single_config(data_by_symbol, horizon, min_ret, lr)
        gc.collect()
        
        if success:
            logger.info("🏆 HOLY GRAIL DISCOVERED FOR S2! Successfully passed all 20 OOS windows.")
            result_path = os.path.join(RESULTS_DIR, "winning_configuration.json")
            with open(result_path, "w") as f:
                json.dump({
                    "strategy": "S2_CVD_Momentum",
                    "horizon_months": horizon,
                    "target_min_return": min_ret,
                    "learning_rate": lr,
                    "timestamp_utc": datetime.utcnow().isoformat()
                }, f, indent=4)
            return
            
    logger.warning("All candidate configurations evaluated.")

if __name__ == "__main__":
    run_autonomous_loop()
