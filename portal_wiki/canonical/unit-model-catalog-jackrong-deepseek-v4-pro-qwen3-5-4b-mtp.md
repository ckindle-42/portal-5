---
id: unit-model-catalog-jackrong-deepseek-v4-pro-qwen3-5-4b-mtp
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/Jackrong/DeepSeek-V4-Pro-Qwen3.5-4B-MTP-GGUF:Q4_K_M`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: f5987f1ea6b0cdb25b66e33a02b95183205d0605
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1786391976.0
updated_at: 1786391976.0
---

`hf.co/Jackrong/DeepSeek-V4-Pro-Qwen3.5-4B-MTP-GGUF:Q4_K_M` is the TASK-BATCH-BENCH-002 Part B.2 intake of the 4B sibling of `bench-jackrong-dsv4-9b` (arch `qwen35`) — a cheap small-reasoner tier candidate. The bare `Jackrong/DeepSeek-V4-Pro-Qwen3.5-4B` repo is safetensors-only (no GGUF at all); found the official `Jackrong/DeepSeek-V4-Pro-Qwen3.5-4B-MTP-GGUF` mirror instead, which uses standard Q4_K_M tag naming (unlike the 9B sibling's repo, no puller issues here) — pulled clean with `ollama pull hf.co/...`. `config/backends.yaml` registers it in the `general` group with `supports_tools: true`, confirmed by a direct `/api/chat` tool-call probe. `config/portal.yaml` gives it the `bench-jackrong-dsv4-4b` workspace `model_hint`.

## Why

The model id, its `general` group placement, and its probed `supports_tools: true` flag are all asserted by `config/backends.yaml`; `config/portal.yaml` supplies the `bench-jackrong-dsv4-4b` workspace binding. Recorded as its own unit (not folded into the 9B's) because the GGUF-availability finding is different — the 4B needed a mirror-repo search, the 9B's own repo had the GGUF directly — so a future session checking "does this Jackrong repo have a GGUF" has both outcomes on record.
