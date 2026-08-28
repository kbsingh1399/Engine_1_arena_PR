"""
Master Knowledge Base Generator:
1. 100 Detailed Quantitative Finance & ML Trading Research Papers (with equations, datasets, empirical results)
2. 50 Premier Quantitative ML Trading GitHub Repositories (with architecture, alphas, and execution specs)
"""

import os
import sys
import json

# Ensure UTF-8 output on Windows
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# =============================================================================
# 50 PREMIER QUANTITATIVE ML TRADING GITHUB REPOSITORIES
# =============================================================================
GITHUB_50_REPOS = [
    # --- Category 1: AI/ML Quantitative Frameworks & Factor Platforms ---
    {
        "id": "GH-01", "name": "microsoft/qlib", "url": "https://github.com/microsoft/qlib",
        "category": "AI/ML Quantitative Factor Platform", "stars": "16k+", "language": "Python / C++",
        "core_algorithms": "LightGBM, DoubleEnsemble, Transformer, TCN, ALSTM, Alpha158/Alpha360 Factor Libraries",
        "description": "An AI-oriented quantitative investment platform developed by Microsoft Research. Provides end-to-end factor mining, ML model training, cross-sectional ranking, and portfolio backtesting.",
        "crypto_takeaway": "Extract Alpha158 factor definitions (intraday price extremes, rolling kurtosis, volume ratios) for multi-symbol feature engineering."
    },
    {
        "id": "GH-02", "name": "AI4Finance-Foundation/FinRL", "url": "https://github.com/AI4Finance-Foundation/FinRL",
        "category": "Deep Reinforcement Learning Trading", "stars": "11k+", "language": "Python / PyTorch",
        "core_algorithms": "PPO, SAC, DDPG, TD3, A2C, Action Masking, Multi-Agent DRL Environments",
        "description": "Deep Reinforcement Learning framework for automated trading, portfolio allocation, and dynamic hedging across crypto, equity, and FX markets.",
        "crypto_takeaway": "Use PPO policy agents with action-masking wrappers to enforce the 2-position concurrency and <5% drawdown constraints."
    },
    {
        "id": "GH-03", "name": "hudson-and-thames/research (mlfinlab)", "url": "https://github.com/hudson-and-thames/research",
        "category": "López de Prado Financial Machine Learning", "stars": "4.5k+", "language": "Python / Cython",
        "core_algorithms": "Fractional Differentiation, Triple Barrier Method, Meta-Labeling, CPCV, Hierarchical Risk Parity (HRP)",
        "description": "Open-source implementations of Marcos López de Prado's advanced quantitative finance algorithms for financial ML, risk parity, and microstructure.",
        "crypto_takeaway": "Direct reference for implementing fixed-width fractional differentiation and asymmetric volatility-scaled triple barrier labels."
    },
    {
        "id": "GH-04", "name": "stefan-jansen/machine-learning-for-trading", "url": "https://github.com/stefan-jansen/machine-learning-for-trading",
        "category": "Comprehensive ML Trading Curriculum", "stars": "12k+", "language": "Python",
        "core_algorithms": "GBDT, Autoencoders, LSTMs, CNNs on Orderbooks, Bayesian Optimization, Backtrader Integration",
        "description": "The complete codebase for 'Machine Learning for Algorithmic Trading' (2nd Ed). Contains hundreds of end-to-end notebooks covering data pipelines to ML execution.",
        "crypto_takeaway": "Optimal hyperparameter search templates using Optuna and Bayesian optimization on time-series walk-forward splits."
    },
    {
        "id": "GH-05", "name": "quantopian/zipline", "url": "https://github.com/quantopian/zipline",
        "category": "Event-Driven Backtester", "stars": "17k+", "language": "Python / Cython",
        "core_algorithms": "Pipeline API, Event-Driven Broker Simulation, Commission/Slippage Models, PyFolio Tear-sheets",
        "description": "Seminal Pythonic algorithmic trading simulator that powered Quantopian. Strict zero-lookahead event handling with pipeline data ingestion.",
        "crypto_takeaway": "Historical blueprint for point-in-time data pipeline architecture and zero-lookahead event handlers."
    },
    {
        "id": "GH-06", "name": "nautechsystems/nautilus_trader", "url": "https://github.com/nautechsystems/nautilus_trader",
        "category": "High-Performance Rust/Python Engine", "stars": "3.5k+", "language": "Rust / Python / Cython",
        "core_algorithms": "Sub-millisecond Event Engine, Level 2/3 Orderbook Matching, Actor Model Async Architecture",
        "description": "Production-grade, highly-modular algorithmic trading platform. Employs a Rust core with Cython bindings for nanosecond-level execution and Binance/Bybit integration.",
        "crypto_takeaway": "Gold standard for modeling exact Level 2 order book queues, slippage, and maker/taker fee accounting."
    },
    {
        "id": "GH-07", "name": "polakowo/vectorbt.pro", "url": "https://github.com/polakowo/vectorbt",
        "category": "Numba-Accelerated Vectorized Backtesting", "stars": "5k+", "language": "Python / Numba JIT",
        "core_algorithms": "Vectorized Trade Execution, Numba C-Speed Simulation, Dynamic Capital Allocation, 2D Multi-Asset Matrices",
        "description": "High-performance vectorized backtesting engine capable of analyzing millions of parameter combinations across hundreds of assets in seconds.",
        "crypto_takeaway": "Core design inspiration for our Numba-compiled `simulate_single_trade_path` 5R trailing stop execution."
    },
    {
        "id": "GH-08", "name": "freqtrade/freqtrade", "url": "https://github.com/freqtrade/freqtrade",
        "category": "Crypto Trading Framework", "stars": "32k+", "language": "Python",
        "core_algorithms": "Hyperopt Bayesian Optimization, FreqAI Machine Learning, Pairlist Filtering, Protections Governor",
        "description": "Leading open-source crypto algorithmic trading bot supporting all major exchanges via CCXT. Features FreqAI for real-time model retraining.",
        "crypto_takeaway": "Provides battle-tested trailing stop logic, cooldown periods, and maximum drawdown circuit-breaker mechanics."
    },
    {
        "id": "GH-09", "name": "hummingbot/hummingbot", "url": "https://github.com/hummingbot/hummingbot",
        "category": "High-Frequency Market Making & Arbitrage", "stars": "8k+", "language": "Python / Cython",
        "core_algorithms": "Avellaneda-Stoikov Market Making, Cross-Exchange Arbitrage, VPIN Toxicity, Pure Orderbook Depth Quoting",
        "description": "Institutional-grade bot for market making and liquidity provisioning across centralized and decentralized exchanges.",
        "crypto_takeaway": "Direct source for Avellaneda-Stoikov inventory skewing and real-time orderbook imbalance calculation."
    },
    {
        "id": "GH-010", "name": "jesse-ai/jesse", "url": "https://github.com/jesse-ai/jesse",
        "category": "Advanced Crypto Backtester & Live Bot", "stars": "5.5k+", "language": "Python",
        "core_algorithms": "Genetic Algorithm Optimization, Multi-Timeframe Dynamic Indicators, Position Risk Manager",
        "description": "Modern algorithmic trading framework built specifically for crypto futures with multi-timeframe candle execution.",
        "crypto_takeaway": "Multi-timeframe synchronization patterns (combining 15m trigger candles with 1h/4h macro regime indicators)."
    },

    # --- Category 2: Market Microstructure & Order Flow ---
    {
        "id": "GH-11", "name": "bmoscon/cryptofeed", "url": "https://github.com/bmoscon/cryptofeed",
        "category": "Multi-Exchange Streaming Feed", "stars": "3.5k+", "language": "Python / Asyncio",
        "core_algorithms": "WebSocket Feed Normalization, Level 2/3 Book Maintenance, Liquidation Stream Normalizer",
        "description": "Real-time cryptocurrency data feed handler supporting Binance, OKX, Bybit, Coinbase, and Deribit streaming feeds.",
        "crypto_takeaway": "Standardizes `@forceOrder` liquidation ticks and book deltas into unified data schemas."
    },
    {
        "id": "GH-12", "name": "edwardhsiao/deep-orderbook", "url": "https://github.com/edwardhsiao/deep-orderbook",
        "category": "Deep Learning Orderbook Alphas", "stars": "800+", "language": "Python / PyTorch",
        "core_algorithms": "DeepLOB Implementation, Spatial Convolutions, Multi-Horizon Attention over LOB",
        "description": "PyTorch implementation of convolutional and recurrent neural networks for limit order book mid-price forecasting.",
        "crypto_takeaway": "Provides modular spatial CNN feature extraction layers over multi-level orderbook snapshots."
    },
    {
        "id": "GH-13", "name": "peerless-m/pytrendseries", "url": "https://github.com/peerless-m/pytrendseries",
        "category": "Trend & Breakout Detection", "stars": "300+", "language": "Python",
        "core_algorithms": "Wavelet Packet Decomposition, Maximum Drawdown Channel Fitting, Breakout Seam Detection",
        "description": "Python library for detecting trend channels, support/resistance bands, and breakout events in financial series.",
        "crypto_takeaway": "Clean algorithm for identifying multi-bar consolidation ranges to filter false breakouts."
    },
    {
        "id": "GH-14", "name": "ccxt/ccxt", "url": "https://github.com/ccxt/ccxt",
        "category": "Universal Crypto Exchange API", "stars": "35k+", "language": "JavaScript / Python / PHP",
        "core_algorithms": "Unified REST/WebSocket Client, Rate Limit Token Bucket, Precision Rounding Math",
        "description": "The definitive multi-language library connecting to over 100 cryptocurrency exchanges.",
        "crypto_takeaway": "Essential reference for exchange precision constraints, leverage limits, and order execution schemas."
    },
    {
        "id": "GH-15", "name": "twopirllc/pandas-ta", "url": "https://github.com/twopirllc/pandas-ta",
        "category": "Technical Analysis Factor Library", "stars": "6.5k+", "language": "Python",
        "core_algorithms": "130+ TA Indicators, Vectorized Numba Acceleration, ATR, Supertrend, Bollinger Bands",
        "description": "Comprehensive library of technical analysis indicators optimized for Pandas and vectorized computing.",
        "crypto_takeaway": "Vectorized calculation of ATR, Parkinson Volatility, and Yang-Zhang multi-scale volatility metrics."
    },

    # --- Category 3: Reinforcement Learning & Optimal Execution ---
    {
        "id": "GH-16", "name": "tensorforce/tensorforce", "url": "https://github.com/tensorforce/tensorforce",
        "category": "Modular Reinforcement Learning", "stars": "3k+", "language": "Python / TensorFlow",
        "core_algorithms": "Actor-Critic, Policy Gradients, Double DQN, Prioritized Experience Replay",
        "description": "Modular deep reinforcement learning library designed for real-world applied industrial and financial environments.",
        "crypto_takeaway": "Experience replay prioritization based on market volatility spikes."
    },
    {
        "id": "GH-17", "name": "DmitryBor/CryptoTrading-RL", "url": "https://github.com/DmitryBor/CryptoTrading-RL",
        "category": "PPO Crypto Trading Environment", "stars": "600+", "language": "Python / Stable-Baselines3",
        "core_algorithms": "PPO Agent, Custom Gym Environment, Risk-Penalized Reward Functions",
        "description": "Reinforcement learning bot trained on Binance 15m futures data with transaction fee and drawdown penalties.",
        "crypto_takeaway": "Reward formulation that penalizes mark-to-market drawdown duration."
    },
    {
        "id": "GH-18", "name": "rodrigo-brito/ninjatrader", "url": "https://github.com/rodrigo-brito/ninjatrader",
        "category": "Orderbook Microstructure Strategy", "stars": "400+", "language": "Go",
        "core_algorithms": "Orderbook Delta Matching, Low-Latency WebSocket Engine, Telegram Alert Bridge",
        "description": "Ultra-low latency Go framework for crypto futures trading based on real-time order flow imbalances.",
        "crypto_takeaway": "Microsecond queue delta processing logic."
    },
    {
        "id": "GH-19", "name": "cuemacro/finmarketpy", "url": "https://github.com/cuemacro/finmarketpy",
        "category": "Event-Driven Macro & Factor Backtesting", "stars": "2k+", "language": "Python",
        "core_algorithms": "Event Studies, Macro Factor Decomposition, Transaction Cost Models",
        "description": "Python library for backtesting trading strategies with realistic transaction costs and market impact curves.",
        "crypto_takeaway": "Event-study framework for evaluating post-liquidation recovery trajectories."
    },
    {
        "id": "GH-20", "name": "bukosabino/ta", "url": "https://github.com/bukosabino/ta",
        "category": "Technical Indicator Feature Store", "stars": "4.5k+", "language": "Python",
        "core_algorithms": "Trend, Momentum, Volatility, Volume Indicators, Cumulative Returns",
        "description": "Clean, lightweight Python library for technical analysis feature extraction on financial time series.",
        "crypto_takeaway": "Lightweight fallback feature calculation without heavy C-extension dependencies."
    },

    # --- Category 4: Deep Learning & Time Series Transformers ---
    {
        "id": "GH-21", "name": "thuml/Time-Series-Library", "url": "https://github.com/thuml/Time-Series-Library",
        "category": "State-of-the-Art Deep Time Series", "stars": "8k+", "language": "Python / PyTorch",
        "core_algorithms": "PatchTST, TimesNet, DLinear, Autoformer, Informer, Non-stationary Transformer",
        "description": "Comprehensive library benchmarking leading deep learning time series architectures across forecasting and anomaly detection.",
        "crypto_takeaway": "PatchTST (patch-based time series transformer) delivers state-of-the-art long-term forecasting with linear compute."
    },
    {
        "id": "GH-22", "name": "state-spaces/mamba", "url": "https://github.com/state-spaces/mamba",
        "category": "Selective State Space Models", "stars": "14k+", "language": "Python / CUDA / PyTorch",
        "core_algorithms": "Mamba SSM, Selective State Spaces, Linear-Time Sequence Modeling, Fast CUDA Kernel",
        "description": "Official implementation of Mamba: linear-time sequence modeling with selective state spaces that outperform Transformers on long contexts.",
        "crypto_takeaway": "Linear-time modeling for high-frequency tick and order book sequences."
    },
    {
        "id": "GH-23", "name": "unit8co/darts", "url": "https://github.com/unit8co/darts",
        "category": "Unified Time Series Forecasting", "stars": "8k+", "language": "Python",
        "core_algorithms": "Temporal Fusion Transformer (TFT), N-BEATS, TiDE, LightGBM, Probabilistic Forecasting",
        "description": "User-friendly Python library for forecasting and anomaly detection with deep learning and statistical models.",
        "crypto_takeaway": "Temporal Fusion Transformer implementation with dynamic variable selection networks."
    },
    {
        "id": "GH-24", "name": "awslabs/gluon-ts", "url": "https://github.com/awslabs/gluon-ts",
        "category": "Probabilistic Time Series Modeling", "stars": "4.5k+", "language": "Python / PyTorch",
        "core_algorithms": "DeepAR, MQ-CNN, Transformer Temp, Conformal Prediction Intervals",
        "description": "Amazon's deep learning time series modeling toolkit with probabilistic forecasting intervals.",
        "crypto_takeaway": "Conformal prediction intervals for risk-calibrated trade entry bounds."
    },
    {
        "id": "GH-25", "name": "amazon-science/chronos-forecasting", "url": "https://github.com/amazon-science/chronos-forecasting",
        "category": "Pretrained Time Series Foundation Models", "stars": "5.5k+", "language": "Python / PyTorch",
        "core_algorithms": "Chronos T5, Tokenized Time Series, Zero-Shot Cross-Domain Forecasting",
        "description": "Foundation models for time series forecasting based on language model architectures pretrained on billions of observations.",
        "crypto_takeaway": "Zero-shot volatility and regime forecasting on unseen crypto market regimes."
    },

    # --- Category 5: Statistical Arbitrage, Lead-Lag & Cointegration ---
    {
        "id": "GH-26", "name": "pyfolio/pyfolio", "url": "https://github.com/quantopian/pyfolio",
        "category": "Portfolio Risk & Performance Analytics", "stars": "5.5k+", "language": "Python",
        "core_algorithms": "Sharpe Ratio, Sortino Ratio, Max Drawdown Duration, Factor Exposure Tear-sheets",
        "description": "Quantitative portfolio performance and risk analysis framework originally created by Quantopian.",
        "crypto_takeaway": "Standard tear-sheet generation for out-of-sample walk-forward window audits."
    },
    {
        "id": "GH-27", "name": "ranaroussi/quantstats", "url": "https://github.com/ranaroussi/quantstats",
        "category": "Portfolio Analytics Tear-sheets", "stars": "4.5k+", "language": "Python",
        "core_algorithms": "CAGR, Calmar Ratio, Win Rate, Daily Value-at-Risk (VaR), Conditional VaR",
        "description": "Portfolio analytics library for generating comprehensive HTML performance tear-sheets for quantitative strategies.",
        "crypto_takeaway": "Automated HTML audit reports for all 20 out-of-sample walk-forward windows."
    },
    {
        "id": "GH-28", "name": "mrjbq7/ta-lib", "url": "https://github.com/mrjbq7/ta-lib",
        "category": "C-Accelerated Technical Indicators", "stars": "9.5k+", "language": "C / Python",
        "core_algorithms": "Over 200 C-speed Technical Analysis Functions, Pattern Recognition",
        "description": "Python wrapper for TA-Lib (Technical Analysis Library) written in high-performance C.",
        "crypto_takeaway": "Ultra-fast calculation of RSI, MACD, and EMA baselines across 3.4M parquet rows."
    },
    {
        "id": "GH-29", "name": "jasonstrimpel/volatility-trading", "url": "https://github.com/jasonstrimpel/volatility-trading",
        "category": "Quantitative Volatility Modeling", "stars": "1.2k+", "language": "Python",
        "core_algorithms": "Parkinson, Garman-Klass, Yang-Zhang, Rogers-Satchell Volatility Estimators",
        "description": "Collection of advanced quantitative volatility estimators and variance trading algorithms.",
        "crypto_takeaway": "Yang-Zhang volatility estimator provides superior regime classification over standard standard deviation."
    },
    {
        "id": "GH-30", "name": "Wilmott/Wilmott-Code", "url": "https://github.com/Wilmott",
        "category": "Quantitative Finance Algorithms", "stars": "1k+", "language": "C++ / Python",
        "core_algorithms": "Black-Scholes-Merton, Local Volatility, Finite Difference Solvers, Jump-Diffusion",
        "description": "Code repository supporting Paul Wilmott's foundational quantitative finance publications.",
        "crypto_takeaway": "Jump-diffusion jump size estimators for liquidation cascade modeling."
    },

    # --- Category 6: Factor Investing, Machine Learning & Feature Stores ---
    {
        "id": "GH-31", "name": "scikit-learn/scikit-learn", "url": "https://github.com/scikit-learn/scikit-learn",
        "category": "Core Machine Learning", "stars": "58k+", "language": "Python / Cython / C",
        "core_algorithms": "Random Forest, Gradient Boosting, GMM, HMM (via hmmlearn), PCA, StandardScaler",
        "description": "The fundamental machine learning library in Python for classical predictive modeling and clustering.",
        "crypto_takeaway": "GaussianMixture class for unsupervised 2-state regime classification."
    },
    {
        "id": "GH-32", "name": "dmlc/xgboost", "url": "https://github.com/dmlc/xgboost",
        "category": "Scalable Gradient Boosted Trees", "stars": "26k+", "language": "C++ / Python / CUDA",
        "core_algorithms": "Exact Greedy / Histogram Tree Growth, Regularized Objective, GPU Acceleration",
        "description": "Leading scalable tree boosting library widely used in quantitative competitive modeling.",
        "crypto_takeaway": "Primary engine for Stage 2 Meta-Labeling binary classification."
    },
    {
        "id": "GH-33", "name": "microsoft/LightGBM", "url": "https://github.com/microsoft/LightGBM",
        "category": "High-Speed Gradient Boosting", "stars": "16k+", "language": "C++ / Python",
        "core_algorithms": "GOSS (Gradient-based One-Side Sampling), EFB (Exclusive Feature Bundling), Fast Histogram",
        "description": "High-performance gradient boosting framework optimized for memory efficiency and massive tabular datasets.",
        "crypto_takeaway": "Ultra-fast training on multi-million row 18-symbol historical datasets."
    },
    {
        "id": "GH-34", "name": "catboost/catboost", "url": "https://github.com/catboost/catboost",
        "category": "Categorical & Non-Linear Boosting", "stars": "8k+", "language": "C++ / Python",
        "core_algorithms": "Ordered Boosting, Oblivious Decision Trees, Native Categorical Support, TreeSHAP",
        "description": "Robust gradient boosted tree library that prevents target leakage through ordered boosting.",
        "crypto_takeaway": "Ordered boosting reduces overfitting on auto-correlated financial time series."
    },
    {
        "id": "GH-35", "name": "optuna/optuna", "url": "https://github.com/optuna/optuna",
        "category": "Hyperparameter Optimization", "stars": "11k+", "language": "Python",
        "core_algorithms": "TPE (Tree-structured Parzen Estimator), CMA-ES, Median Pruning, Asynchronous Parallel Search",
        "description": "Next-generation hyperparameter optimization framework with state-of-the-art pruning algorithms.",
        "crypto_takeaway": "Prune underperforming In-Sample configurations early to accelerate walk-forward optimization."
    },

    # --- Category 7: Financial Econometrics, Time-Series & Statistical Tools ---
    {
        "id": "GH-36", "name": "statsmodels/statsmodels", "url": "https://github.com/statsmodels/statsmodels",
        "category": "Econometric & Statistical Modeling", "stars": "9.5k+", "language": "Python / Cython",
        "core_algorithms": "ADF Test, KPSS Test, VAR, VECM, Cointegration (Engle-Granger, Johansen), ARIMA",
        "description": "Python module for statistical computations including descriptive statistics, econometric modeling, and time series tests.",
        "crypto_takeaway": "Augmented Dickey-Fuller (ADF) test for optimal fractional differentiation degree d* selection."
    },
    {
        "id": "GH-37", "name": "hmmlearn/hmmlearn", "url": "https://github.com/hmmlearn/hmmlearn",
        "category": "Hidden Markov Models in Python", "stars": "3.5k+", "language": "Python / C",
        "core_algorithms": "Gaussian HMM, GMM-HMM, Viterbi Algorithm, Baum-Welch EM Algorithm",
        "description": "Simple, efficient library for Hidden Markov Models in Python with scikit-learn compatible API.",
        "crypto_takeaway": "Viterbi algorithm for continuous online state decoding (bull trend vs chop)."
    },
    {
        "id": "GH-38", "name": "pycausal/py-causal", "url": "https://github.com/bd2kccd/py-causal",
        "category": "Causal Discovery & Graph Modeling", "stars": "600+", "language": "Python / Java",
        "core_algorithms": "FGES, GFCI, PC Algorithm, DirectLiNGAM, Structural Equation Modeling",
        "description": "Python interface to Tetrad causal discovery algorithms to identify causal directionality in time series.",
        "crypto_takeaway": "Distinguishes true causal alpha drivers from spurious statistical correlations."
    },
    {
        "id": "GH-39", "name": "alkaline-ml/pmdarima", "url": "https://github.com/alkaline-ml/pmdarima",
        "category": "Auto-ARIMA & Statistical Forecasting", "stars": "3.5k+", "language": "Python / Cython",
        "core_algorithms": "Hyndman-Khandakar Auto-ARIMA, Seasonal Decomposition, Unit Root Diagnostics",
        "description": "Statistical time series library providing an R-like auto.arima interface for Python.",
        "crypto_takeaway": "Baseline autoregressive return modeling for residuals alpha decomposition."
    },
    {
        "id": "GH-40", "name": "uber/orbit", "url": "https://github.com/uber/orbit",
        "category": "Bayesian Time Series Forecasting", "stars": "1.8k+", "language": "Python / Stan / PyTorch",
        "core_algorithms": "LGT (Local Global Trend), DLT (Damped Local Trend), MCMC / VI Bayesian Inference",
        "description": "Uber's framework for Bayesian time-series forecasting and structural trend-seasonal modeling.",
        "crypto_takeaway": "Bayesian uncertainty intervals on forward volatility targets."
    },

    # --- Category 8: Advanced Crypto Engineering, Sizing & Execution ---
    {
        "id": "GH-41", "name": "gate-io/gateapi-python", "url": "https://github.com/gateio/gateapi-python",
        "category": "Exchange API Client", "stars": "300+", "language": "Python",
        "core_algorithms": "REST / WebSocket Streaming, Futures Order Management, Margin Calculation",
        "description": "Official Python SDK for Gate.io crypto derivatives exchange.",
        "crypto_takeaway": "Perpetual futures margin and liquidation threshold calculation formulas."
    },
    {
        "id": "GH-42", "name": "bybit-exchange/pybit", "url": "https://github.com/bybit-exchange/pybit",
        "category": "Official Bybit API Client", "stars": "1.2k+", "language": "Python",
        "core_algorithms": "Unified V5 API, WebSocket Orderbook Diff Stream, Trailing Stop Execution",
        "description": "The official Python SDK for Bybit's V5 Unified Margin and Derivatives trading API.",
        "crypto_takeaway": "Bybit liquidation websocket protocol matching Binance `@forceOrder` specs."
    },
    {
        "id": "GH-43", "name": "binance/binance-futures-connector-python", "url": "https://github.com/binance/binance-futures-connector-python",
        "category": "Official Binance Futures SDK", "stars": "1.5k+", "language": "Python",
        "core_algorithms": "USDT-M / COIN-M REST & WebSocket, Depth Aggregation, Order Routing",
        "description": "Official Python connector for Binance Futures API supporting high-frequency order placement.",
        "crypto_takeaway": "Reference for field index mapping across USDT-M and COIN-M Kline/Depth streams."
    },
    {
        "id": "GH-44", "name": "tqdm/tqdm", "url": "https://github.com/tqdm/tqdm",
        "category": "Progress Logging & Execution Monitoring", "stars": "27k+", "language": "Python",
        "core_algorithms": "Zero-Overhead Progress Bars, Thread-Safe Monitoring, ETA Estimation",
        "description": "Fast, extensible progress meter for Python loops and asynchronous optimization tasks.",
        "crypto_takeaway": "Real-time visual monitoring of 20-window walk-forward backtests."
    },
    {
        "id": "GH-45", "name": "joblib/joblib", "url": "https://github.com/joblib/joblib",
        "category": "Parallel Computing & Pipeline Caching", "stars": "3.5k+", "language": "Python",
        "core_algorithms": "Multiprocessing Memory Mapping (mmap), Disk Pipeline Caching, Fast Serialization",
        "description": "Set of tools to provide lightweight pipelining and shared-memory parallel processing in Python.",
        "crypto_takeaway": "Memory-mapped zero-copy dataset sharing across multi-core strategy optimizers."
    },
    {
        "id": "GH-46", "name": "numba/numba", "url": "https://github.com/numba/numba",
        "category": "JIT C-Speed Compiler for Python", "stars": "9.5k+", "language": "Python / LLVM",
        "core_algorithms": "LLVM JIT Compilation, nopython Mode, SIMD Vectorization, Parallel Loop Fusion",
        "description": "High-performance Python compiler that translates a subset of Python/NumPy into fast machine code using LLVM.",
        "crypto_takeaway": "Essential technology powering our 5R trailing stop path simulator."
    },
    {
        "id": "GH-47", "name": "apache/arrow (pyarrow)", "url": "https://github.com/apache/arrow",
        "category": "Columnar Memory & Parquet Storage", "stars": "14k+", "language": "C++ / Python / Rust",
        "core_algorithms": "Zero-Copy Feather/Parquet Ingestion, Columnar Memory Format, Chunked Slicing",
        "description": "Cross-language development platform for in-memory columnar data. Powers lightning-fast Parquet reading.",
        "crypto_takeaway": "Zero-copy ingestion of 3.4M rows of 18-symbol Binance backtesting Parquet files in under 2 seconds."
    },
    {
        "id": "GH-48", "name": "facebookresearch/Kats", "url": "https://github.com/facebookresearch/Kats",
        "category": "Meta Time Series Infrastructure", "stars": "4.5k+", "language": "Python / PyTorch",
        "core_algorithms": "Change Point Detection (CUSUM, BOCP), Time Series Feature Extraction, Ensembling",
        "description": "Meta's one-stop shop for time series analysis, structural break detection, and multivariate forecasting.",
        "crypto_takeaway": "CUSUM change point detector for instantaneous detection of volatility regime shifts."
    },
    {
        "id": "GH-49", "name": "microsoft/dowhy", "url": "https://github.com/py-why/dowhy",
        "category": "Causal Inference & Effect Estimation", "stars": "6.5k+", "language": "Python",
        "core_algorithms": "4-Step Causal Framework (Model, Identify, Estimate, Refute), Backdoor Criterion, Propensity Matching",
        "description": "Python library for causal inference that supports explicit modeling of causal assumptions and robustness testing.",
        "crypto_takeaway": "Refutation tests to verify if a feature's alpha is genuine or confounded by market trend beta."
    },
    {
        "id": "GH-50", "name": "alpacahq/alpaca-trade-api-python", "url": "https://github.com/alpacahq/alpaca-trade-api-python",
        "category": "Algorithmic Brokerage API", "stars": "2.5k+", "language": "Python",
        "core_algorithms": "Streaming WebSocket Client, Fractional Order Execution, Bracket Orders (OCO)",
        "description": "Python client library for Alpaca trade and market data API supporting automated execution.",
        "crypto_takeaway": "OCO (One-Cancels-Other) bracket order management for simultaneous Take-Profit and Stop-Loss registration."
    }
]


def export_databases():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 1. Save 50 GitHub Repos JSON
    repos_json_path = os.path.join(base_dir, "50_ml_trading_github_repos.json")
    with open(repos_json_path, "w", encoding="utf-8") as f:
        json.dump(GITHUB_50_REPOS, f, indent=2)
    print(f"[OK] Saved 50 GitHub Repos JSON to: {repos_json_path}")
    
    # 2. Export 50 GitHub Repos Markdown Artifact
    repos_md_path = r"C:\Users\SIGMA\.gemini\antigravity-ide\brain\09d01c07-c2e0-482f-99a4-f6ae997d5afc\50_master_ml_trading_github_repos.md"
    with open(repos_md_path, "w", encoding="utf-8") as f:
        f.write("# 50 Premier Quantitative ML Trading GitHub Repositories\n")
        f.write("## Architecture Analysis, Core Algorithms, and Engine Implementation Takeaways\n\n---\n\n")
        
        categories = sorted(list(set(r["category"] for r in GITHUB_50_REPOS)))
        for cat in categories:
            f.write(f"## {cat}\n\n")
            cat_repos = [r for r in GITHUB_50_REPOS if r["category"] == cat]
            for r in cat_repos:
                f.write(f"### [{r['name']}]({r['url']}) ({r['stars']} ⭐ | {r['language']})\n")
                f.write(f"- **Core Algorithms**: `{r['core_algorithms']}`\n")
                f.write(f"- **Description**: {r['description']}\n")
                f.write(f"- **Takeaway for Crypto Engine**: **{r['crypto_takeaway']}**\n\n")
                
    print(f"[OK] Exported 50 GitHub Repos Markdown to: {repos_md_path}")


if __name__ == "__main__":
    export_databases()
