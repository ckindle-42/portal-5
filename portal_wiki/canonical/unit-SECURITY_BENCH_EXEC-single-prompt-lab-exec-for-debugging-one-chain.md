---
id: unit-SECURITY_BENCH_EXEC-single-prompt-lab-exec-for-debugging-one-chain
kind: why
title: "SECURITY_BENCH_EXEC \u2014 Single prompt, lab-exec (for debugging one chain)"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: Single prompt, lab-exec (for debugging one chain)
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC
created_at: 1783195000.900633
updated_at: 1783195000.900633
---


```bash
python3 -m tests.benchmarks.bench_security \
  --skip-workspace-bench \
  --exec-chain-models \
    "hf.co/mradermacher/VulnLLM-R-7B-GGUF:Q4_K_M" \
    "qwen3-coder:30b-a3b-q4_K_M" \
    "huihui_ai/baronllm-abliterated:latest" \
  --blue-defender "hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0" \
  --prompt kerberoasting \
  --lab-exec \
  2>&1 | tee /tmp/secbench_kerberoast.log
```
