---
name: engine-1
description: Entry skill for the Engine 1 crypto trading engine — core files, conventions, and the installed skill stack.
---

# Engine 1 — Project Skill

Working skill for the `Engine_1_arena_PR` repo (crypto liquidation/trading engine + CoinGlass parity tooling).

## When to use
Any task in this repository: code changes to the engine, data pipeline work, ML calibration, parity audits, or agent orchestration.

## Instructions
1. Core code: `Engine_1.py` (main engine), `binance_broker.py` (broker/execution), `coinglass_scraper.py` + `coinglass_parity_engine/` (data & parity).
2. Project conventions live in `.agents/` — rules in `.agents/rules/`, persistent agent memory in `.agents/memory/` (start with `MEMORY.md` and `project-conventions.md`).
3. Installed skill stack (see `.agents/memory/skills_stack.md`):
   - `.agents/skills/` — Karpathy coding guidelines + all 37 Matt Pocock skills (grilling, spec flow, TDD, code review, etc.)
   - `~/.agents/skills/` — Antigravity Awesome Skills full library (1,935 skills, global)
   - `prime` CLI — Prime Intellect ML/compute (use `--plain`; requires user login)
4. For ML/heavy-compute work: use the `prime` CLI (hosted training, GPU availability, RL envs).
5. Follow Karpathy guidelines for all code changes: state assumptions, keep changes surgical, verify against explicit success criteria.
