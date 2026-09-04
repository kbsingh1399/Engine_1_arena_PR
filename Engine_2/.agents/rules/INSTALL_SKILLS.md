# 🛠️ AGENT SKILLS MASTER INSTALLATION & REPOSITORY DIRECTORY

This document contains the complete, verified installation commands for all machine learning, quantitative finance, high-performance data engineering, and agentic architecture skills.

---

## ⚠️ Important Note on `skillfish` Command Syntax
When using `skillfish`, you cannot pass internal marketplace slugs (e.g. `mp-liquidation-risk-84e87a42`), because `skillfish` resolves directly against public GitHub repositories. 

**Correct Syntax:**
```powershell
npx skillfish add <github_owner>/<github_repo> [<skill_name>] [flags]
```

---

## 🚀 1. The Master One-Liner (Automated Multi-Repo Installer)
Run this single Python command in your terminal to instantly download and install all **2,200+ ML, Quant, Architecture, and Technical Skills** from the four primary repositories directly into `.agents/skills`:

```powershell
python -c "import urllib.request, json, os; from pathlib import Path; target = Path('.agents/skills'); target.mkdir(parents=True, exist_ok=True); repos = ['sickn33/antigravity-awesome-skills', 'jeremylongshore/claude-code-plugins-plus-skills', 'ruvnet/ruflo', 'affaan-m/everything-claude-code', 'terrylica/cc-skills']; keywords = ['ml', 'data', 'quant', 'algo', 'python', 'performance', 'profil', 'test', 'tdd', 'math', 'stat', 'neural', 'torch', 'xgboost', 'feature', 'timeseries', 'architecture', 'debug', 'optimization', 'cuda', 'gpu', 'pipeline', 'clickhouse', 'polars']; [([Path(target/p.split('/')[-2]).mkdir(parents=True, exist_ok=True), (target/p.split('/')[-2]/'SKILL.md').write_text(urllib.request.urlopen(urllib.request.Request(f'https://raw.githubusercontent.com/{r}/main/{p}', headers={'User-Agent':'Mozilla/5.0'})).read().decode('utf-8'), encoding='utf-8'), print(f'✓ Installed: {p.split('/')[-2]}')] for r in repos for p in [i['path'] for i in json.loads(urllib.request.urlopen(urllib.request.Request(f'https://api.github.com/repos/{r}/git/trees/main?recursive=1', headers={'User-Agent':'Mozilla/5.0'})).read().decode('utf-8')).get('tree', []) if i['path'].endswith('SKILL.md')] if any(k in p.lower() for k in keywords))]"
```

---

## 📦 2. Targeted `npx skillfish` Commands by Category

### A. Machine Learning, Deep Learning & Tabular Models
```powershell
# PyTorch Development & Idiomatic Patterns
npx skillfish add affaan-m/everything-claude-code pytorch-patterns -y --force

# ML Data Pipelines (Polars, Apache Arrow, ClickHouse)
npx skillfish add terrylica/cc-skills ml-data-pipeline-architecture -y --force

# Production ML Engineering & Data Contracts
npx skillfish add affaan-m/everything-claude-code mle-workflow -y --force

# Gradient Boosting & Tabular ML Toolkit (XGBoost / LightGBM)
npx skillfish add ruvnet/ruflo agent-data-ml-model -y --force

# Neural Architecture & Training Systems
npx skillfish add ruvnet/ruflo agent-neural-network -y --force
npx skillfish add ruvnet/ruflo agent-safla-neural -y --force
```

### B. Quantitative Trading, Risk & Market Architecture
```powershell
# Trading Risk & Sizing Optimizer (Portfolio VaR, CVaR, Dynamic Sizing)
npx skillfish add ruvnet/ruflo trader-risk -y --force

# Backtesting & Walk-Forward Optimization
npx skillfish add ruvnet/ruflo trader-backtest -y --force
npx skillfish add ruvnet/ruflo backtesting-trading-strategies -y --force

# Market Order Flow & Pattern Ingestion (OHLCV & Footprint Vectors)
npx skillfish add ruvnet/ruflo market-ingest -y --force
npx skillfish add ruvnet/ruflo market-pattern -y --force

# Multi-Agent Trading Brain Orchestration
npx skillfish add ruvnet/ruflo agent-squad -y --force
```

### C. Database Performance, Time-Series & ClickHouse
```powershell
# ClickHouse Query Optimization & Analytical Schemas
npx skillfish add affaan-m/everything-claude-code clickhouse-performance-tuning -y --force

# PostgreSQL Performance & Connection Pooling
npx skillfish add affaan-m/everything-claude-code postgresql-optimization -y --force

# Redis Caching & Pub/Sub Patterns
npx skillfish add affaan-m/everything-claude-code redis-cache-manager -y --force

# Time-Series Forecasting & Analysis
npx skillfish add affaan-m/everything-claude-code time-series-decomposer -y --force
npx skillfish add affaan-m/everything-claude-code forecasting-time-series-data -y --force
```

### D. Developer Tools, GPU Acceleration & Architecture
```powershell
# Andrej Karpathy Coding Guidelines (Simplicity First, Surgical Changes)
npx skillfish add multica-ai/andrej-karpathy-skills --all -y --force

# Matt Pocock Agentic Skills Suite (37 Specialized Skills)
npx skillfish add mattpocock/skills --all -y --force

# Python Performance Optimization & Linting
npx skillfish add affaan-m/everything-claude-code python-performance-optimization -y --force

# Systematic Debugging & Error Diagnosis
npx skillfish add affaan-m/everything-claude-code systematic-debugging -y --force
npx skillfish add affaan-m/everything-claude-code error-diagnostics-smart-debug -y --force

# Code Quality & Benchmark Suites
npx skillfish add ruvnet/ruflo agent-analyze-code-quality -y --force
npx skillfish add ruvnet/ruflo agent-benchmark-suite -y --force
```

---

## ⚡ 3. Single Copy-Paste Batch Script (All Top Skills)
Copy and paste this block into PowerShell to install the most vital skills directly:

```powershell
npx skillfish add multica-ai/andrej-karpathy-skills --all -y --force;
npx skillfish add mattpocock/skills --all -y --force;
npx skillfish add affaan-m/everything-claude-code pytorch-patterns -y --force;
npx skillfish add terrylica/cc-skills ml-data-pipeline-architecture -y --force;
npx skillfish add ruvnet/ruflo trader-risk -y --force;
npx skillfish add ruvnet/ruflo market-ingest -y --force;
npx skillfish add ruvnet/ruflo agent-data-ml-model -y --force;
npx skillfish add ruvnet/ruflo agent-analyze-code-quality -y --force;
npx skillfish add affaan-m/everything-claude-code systematic-debugging -y --force;
npx skillfish add affaan-m/everything-claude-code clickhouse-performance-tuning -y --force;
npx skillfish add affaan-m/everything-claude-code python-performance-optimization -y --force
```
