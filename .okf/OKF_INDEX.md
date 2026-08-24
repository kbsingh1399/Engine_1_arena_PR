---
type: okf_index
title: Open Knowledge Format Master Index
version: 1.0.0
last_updated: 2026-08-24
standard: Google Cloud Open Knowledge Format (OKF v0.2)
tags: [okf, index, agent_memory, architecture]
---

# Open Knowledge Format (OKF) Master Index

This repository implements the **Open Knowledge Format (OKF)** standard to solve the agent memory problem for **known-knowns** (deterministic architecture, verified formulas, indicator contracts, and runbooks).

## 📁 OKF Knowledge Base

| Knowledge Item | Domain | Description | Verification Target |
|---|---|---|---|
| [depth_orderbook.md](file:///c:/Users/SIGMA/Documents/Project%20-%20Coinglass%20Trading/Engine_1_arena_PR/.okf/indicators/depth_orderbook.md) | `market_data.orderbook` | ±1% Depth scaling for Binance-only preset | CoinGlass `BGfPJm` & `GTmNoY` |
| [cvd_session.md](file:///c:/Users/SIGMA/Documents/Project%20-%20Coinglass%20Trading/Engine_1_arena_PR/.okf/indicators/cvd_session.md) | `market_data.cvd` | 880-bar seed and real-time trade CVD aggregation | CoinGlass `7Tvo2z` & `HMc6PC` |
| [candle_rollover.md](file:///c:/Users/SIGMA/Documents/Project%20-%20Coinglass%20Trading/Engine_1_arena_PR/.okf/indicators/candle_rollover.md) | `market_data.lifecycle` | Sub-second 15m boundary zero-reset protocol | CoinGlass 15m candle rollover |
| [footprint_seeding.md](file:///c:/Users/SIGMA/Documents/Project%20-%20Coinglass%20Trading/Engine_1_arena_PR/.okf/indicators/footprint_seeding.md) | `market_data.footprint` | 1m Kline distribution to safely reconstruct mid-candle footprints | Avoids Binance WAF 418 bans |
| [cvd_auto_anchor.md](file:///c:/Users/SIGMA/Documents/Project%20-%20Coinglass%20Trading/Engine_1_arena_PR/.okf/indicators/cvd_auto_anchor.md) | `market_data.cvd` | Dual-mode auto-calibrating cold-start persistence for live ML | Independent headless boot |
| [whale_index.md](file:///c:/Users/SIGMA/Documents/Project%20-%20Coinglass%20Trading/Engine_1_arena_PR/.okf/indicators/whale_index.md) | `market_data.microstructure` | Whale Index mathematical parity formula (TopTrader_LS - 1.0) * 100 | CoinGlass Whale Index Study |

## 🧠 Memory Paradigm: OKF + RAG
- **OKF**: Solves deterministic memory (known-knowns: formulas, scalars, protocol rules) via version-controlled Markdown + YAML frontmatter.
- **RAG / Code Graph**: Solves unstructured dynamic retrieval via Tree-Sitter AST (`code-review-graph`) and session transcripts.
