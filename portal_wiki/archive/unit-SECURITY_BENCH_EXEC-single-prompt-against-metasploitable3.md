---
id: unit-SECURITY_BENCH_EXEC-single-prompt-against-metasploitable3
historical: true
kind: why
title: "SECURITY_BENCH_EXEC \u2014 Single prompt against Metasploitable3"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: Single prompt against Metasploitable3
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC

---


```bash
python3 -m tests.benchmarks.bench_security \
  --skip-workspace-bench \
  --exec-chain-models "hf.co/mradermacher/VulnLLM-R-7B-GGUF:Q4_K_M" \
  --prompt eternalblue_ms17010 \
  --lab-exec \
  2>&1 | tee /tmp/secbench_eternalblue.log
```
