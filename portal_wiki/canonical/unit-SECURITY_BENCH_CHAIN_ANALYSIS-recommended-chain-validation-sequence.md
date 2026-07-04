---
id: unit-SECURITY_BENCH_CHAIN_ANALYSIS-recommended-chain-validation-sequence
kind: why
title: "SECURITY_BENCH_CHAIN_ANALYSIS \u2014 Recommended Chain Validation Sequence"
sources:
- type: design
  path: docs/SECURITY_BENCH_CHAIN_ANALYSIS.md
  section: Recommended Chain Validation Sequence
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_CHAIN_ANALYSIS
created_at: 1783195000.8946629
updated_at: 1783195000.8946629
---


When evaluating a new chain model:

1. `linux_privesc × auto-pentest` — gate: exec_composite ≥ 0.80, tool_utilization ≥ 4/6
2. `kerberoasting × auto-purpleteam-exec` — gate: exec_composite ≥ 0.80
3. `redis_to_rce × auto-pentest` — gate: exec_composite ≥ 0.85 (was a hard regression indicator)
4. If all 3 pass, run full 10-prompt × 2-workspace suite

---
