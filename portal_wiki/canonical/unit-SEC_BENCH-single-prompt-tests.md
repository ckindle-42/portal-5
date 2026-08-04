---
id: unit-SEC_BENCH-single-prompt-tests
kind: what
title: Security bench single-prompt quick tests
sources:
- type: code
  path: portal/modules/security/core/cli.py
last_generated_commit: 0a5fcb6eea38bf284a96ceea702849491ba4d1c7
claims: []
confidence: high
tags:
- bench
- security
- testing
- verified-v1
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
  --blue-defender-model "hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0" \
  --prompt kerberoasting \
  --lab-exec \
  2>&1 | tee /tmp/secbench_kerberoast.log
```

`--skip-workspace-bench` skips the theory/exec pipeline passes so only the chain runs; `--exec-chain-models` takes the 2-4 model roster; `--blue-defender-model` names the SOC-analysis model; `--prompt` selects a single `PROMPTS` key; `--lab-exec` enables real dispatch.

## Probe lab services only

```bash
python3 -m portal.modules.security.core --probe-lab --dry-run 2>&1
```

## Why

These two commands are the fastest paths to a single answer: run one prompt end-to-end against the live lab, or just check reachability before committing to a long run. The single-prompt form is also the debugging loop — when a full scenario fails, isolating one prompt with one model roster makes the failure reproducible in minutes instead of hours.
