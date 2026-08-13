---
id: unit-model-catalog-jackrong-deepseek-v4-pro-qwen3-5-9b-mtp
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/Jackrong/DeepSeek-V4-Pro-Qwen3.5-9B-MTP-GGUF:Q4_K_M`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 75c5054f791636f367b62a1776bcc9f631794766
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1786390650.0
updated_at: 1786390650.0
---

`hf.co/Jackrong/DeepSeek-V4-Pro-Qwen3.5-9B-MTP-GGUF:Q4_K_M` is the TASK-BATCH-BENCH-002 Part B.1 intake of Jackrong's DeepSeek-V4-Pro→Qwen3.5-9B reasoning distill (arch `qwen35`, ~5.8GB, embedded MTP draft heads, card claims 97.2% format-compliance) — a distillation-watch datapoint (Jackrong is on the watchlist per the `bench-qwopus-coder-mtp-v2` precedent) and a math/STEM reasoning candidate. Pulled clean with no arch errors (GATE-0b), standard `ollama pull hf.co/...` path, no workaround needed. `config/backends.yaml` registers it in the `general` group with `supports_tools: true`, confirmed by a direct `/api/chat` tool-call probe (clean, well-formed `tool_calls`). `config/portal.yaml` gives it the `bench-jackrong-dsv4-9b` workspace `model_hint`. Self-reported card benches (97.2% compliance) are UNVERIFIED until reproduced on this harness.

## Why

The model id, its `general` group placement, and its probed `supports_tools: true` flag are all asserted by `config/backends.yaml`; `config/portal.yaml` supplies the `bench-jackrong-dsv4-9b` workspace binding. Kept as a distillation-watch record separate from the Muse-Glimmer/Deepwen units so a future session evaluating another Jackrong release can find the prior verdict pattern for this uploader in one place.
