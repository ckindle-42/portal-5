---
id: unit-MLX_CHANGES_2026-04-26-2-speculative-decoding-broken-arrayscache-not-trim
kind: why
title: "MLX_CHANGES_2026-04-26 \u2014 2. Speculative Decoding Broken \u2014 `ArraysCache`\
  \ Not Trimmable"
sources:
- type: design
  path: docs/MLX_CHANGES_2026-04-26.md
  section: "2. Speculative Decoding Broken \u2014 `ArraysCache` Not Trimmable"
last_generated_commit: ''
confidence: high
tags:
- docs
- MLX_CHANGES_2026-04-26
created_at: 1783195000.8763719
updated_at: 1783195000.8763719
---

- **Severity**: Medium — spec-decoding disabled, loses ~10-20% TPS on supported models
- **Symptom**: `ValueError: Speculative decoding requires a trimmable prompt cache (got {'ArraysCache'}).`
- **Root cause**: mlx_lm 0.31.2 changed default prompt cache from trimmable type to `ArraysCache`. Speculative decoding requires cache trimming to work.
- **Fix applied**: `config/backends.yaml` `speculative_decoding.draft_models` set to `{}` (disabled).
- **Affected models** (were using draft models): Qwen3-Coder-30B, DeepSeek-R1-Distill-Qwen-32B (both 4bit and 8bit), Jackrong/Qwopus3.5-27B, Jackrong/Qwen3.5-27B, Jackrong/Qwen3.5-35B, Llama-3.3-70B
- **Status**: Disabled. Re-enable when mlx_lm fixes cache compatibility.
