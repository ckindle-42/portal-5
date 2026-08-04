---
id: unit-SECURITY_BENCH_EXEC-chain-structure-3-models-2-rounds-6-turns
kind: why
title: "SECURITY_BENCH_EXEC \u2014 Chain structure (3 models \xD7 2 rounds = 6 turns)"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: "Chain structure (3 models \xD7 2 rounds = 6 turns)"
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC
created_at: 1783195000.909188
updated_at: 1783195000.909188
---


```
[Round 1]
  VulnLLM-R-7B  → assigned: step 0 (recon)    → calls execute_bash → real output
  Qwable-35B    → assigned: step 1 (kerberoast) → calls execute_bash → real output
  BaronLLM      → assigned: step 2 (crack)       → calls execute_bash → real output
[Round 2]
  VulnLLM-R-7B  → re-attempts missed steps (with fallback_techniques)
  Qwable-35B    → re-attempts
  BaronLLM      → re-attempts

After each model turn: blue defender sees real terminal output, generates MITRE detection.
  If --blue-active: blue can deploy block_ip / disable_account / revoke_tgt countermeasures.
After full chain: blue runs final holistic analysis.
```
