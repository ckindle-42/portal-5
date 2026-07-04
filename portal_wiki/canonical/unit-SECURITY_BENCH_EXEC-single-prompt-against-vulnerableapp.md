---
id: unit-SECURITY_BENCH_EXEC-single-prompt-against-vulnerableapp
kind: why
title: "SECURITY_BENCH_EXEC \u2014 Single prompt against VulnerableApp"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: Single prompt against VulnerableApp
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC
created_at: 1783195000.901115
updated_at: 1783195000.901115
---


```bash
python3 -m tests.benchmarks.bench_security \
  --skip-workspace-bench \
  --exec-chain-models "hf.co/mradermacher/VulnLLM-R-7B-GGUF:Q4_K_M" \
  --prompt sqli_manual \
  --lab-exec \
  2>&1 | tee /tmp/secbench_sqli.log
```
