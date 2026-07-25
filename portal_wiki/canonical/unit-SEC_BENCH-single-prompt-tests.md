---
id: unit-SEC_BENCH-single-prompt-tests
kind: what
title: Security bench single-prompt quick tests
sources:
- type: doc
  path: docs/SECURITY_BENCH_EXEC.md
  commit: ddb1cc61
last_generated_commit: ddb1cc61
confidence: high
tags:
- security
- bench
- testing
created_at: 1784945480.185725
updated_at: 1784945480.185725
---

## Single prompt, lab-exec

```bash
python3 -m portal.modules.security.core \
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

## Probe lab services only

```bash
python3 -m portal.modules.security.core --probe-lab --dry-run 2>&1
```
