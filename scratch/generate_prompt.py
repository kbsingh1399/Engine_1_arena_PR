import os

prompt_content = """# Claude Fable 5 - Layer 2 Defense & Validation Audit

**Role:** You are a Principal Quantitative Systems Architect and Python Async Expert, specializing in defending and validating high-frequency trading (HFT) architectures against brutal external audits. 

**Objective:** We recently submitted our live execution engine (`Engine_1.py`) to a "Layer 1 Attack" audit under the strict "Fable 5 Milestone" standards. The auditor (an elite external model) produced a highly critical report citing 9 CRITICAL defects and 6 WARNING defects. 

Your task is to conduct a **Layer 2 Defense**:
1. Fetch and read the provided source code of `Engine_1.py` from the Git repository (details below).
2. Compare the actual code against the auditor's critique (provided below).
3. Validate which of the auditor's findings are **real vulnerabilities** present in our code, and which are **hallucinations/inapplicable** because the auditor lacked full context.
4. For every **real** vulnerability confirmed, provide the **exact, robust code remediation (patches)** required to fix it and achieve Fable 5 compliance.

## Target Repository Context
Please fetch the code from the following location before answering:
- **Repository:** `https://github.com/kbsingh1399/coinglass-trading`
- **Branch:** `arena/019fec7a-coinglass-trading`
- **Target File:** `/Engine_1_arena_PR/Engine_1.py`
- **Reference Commit:** `76768127`

## The Auditor's Critique (Layer 1 Attack)
```
[CRITICAL] A-1 — CVD 15-Minute Rollover Boundary Uses math.isclose() on Floating-Point Timestamps
[CRITICAL] A-2 — Z-Score Normalization Window Is Being Applied to a Live Deque That Is Pre-Padded With REST Warmup Data of Different Resolution
[CRITICAL] A-3 — Indicator State Is Recalculated on Every Tick Without Stateful Incremental Update
[CRITICAL] B-1 — IOC Order Execution Is Synchronous Inside the WebSocket Message Handler
[CRITICAL] B-2 — Background Tasks Are Being Created with asyncio.create_task() But Never Stored or Awaited
[CRITICAL] B-3 — Database Write Is Awaited Inline in the Signal Path, Blocking WebSocket Processing
[CRITICAL] C-1 — Partial Fill Handling Is Missing or Incorrect: Weighted Average Price Calculation Is Broken
[CRITICAL] C-2 — State Is Not Reset When IOC Order Is Fully Rejected: System Believes It Holds a Position It Does Not
[CRITICAL] C-3 — No Exponential Backoff on HTTP 429 (Rate Limit) or 418 (IP Ban)
[CRITICAL] C-4 — IOC Limit Price Is Computed From Last WebSocket Tick Price, Not From Order Book Mid-Price
[WARNING] D-1 — Duplicate Candle Ingestion at the REST-to-WebSocket Seam
[WARNING] D-2 — deque(maxlen=1200) Does Not Protect Against REST Warmup Overfilling
[WARNING] D-3 — Rolling Deque's maxlen Creates a False Sense of Memory Safety: numpy Array Conversion Creates a Full Copy
[WARNING] D-4 — No Monotonicity Check on Incoming Bar Timestamps
[WARNING] D-5 — Memory Deque Survives Reconnection Without Flush
```

## Output Requirements
1. **Validation Report:** For each of the auditor's findings, explicitly state `[CONFIRMED]` if the vulnerability exists in the provided code, or `[REJECTED]` if the code already handles it properly or the finding is inapplicable. Provide a 1-2 sentence justification referencing the specific line numbers or functions in the code.
2. **Remediation Plan:** For every `[CONFIRMED]` defect, provide the exact code patches (using `diff` or targeted code blocks) to fix the issue. The fixes must strictly adhere to the Fable 5 Iron Laws (Absolute Async Resilience, Strict Mathematical Parity, Capital Preservation).

*Begin your Layer 2 Defense.*
"""

output_file = "C:\\Users\\SIGMA\\Documents\\Project - Coinglass Trading\\Engine_1_arena_PR\\scratch\\layer_2_defense_prompt.md"
with open(output_file, "w", encoding="utf-8") as f:
    f.write(prompt_content)

print(f"Generated {output_file}")
