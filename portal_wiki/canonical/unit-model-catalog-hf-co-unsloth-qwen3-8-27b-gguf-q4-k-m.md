---
id: unit-model-catalog-hf-co-unsloth-qwen3-8-27b-gguf-q4-k-m
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
- type: code
  path: config/personas/qwen38coder.yaml
last_generated_commit: 64c5f5f41652bf67e97863ee1a6285289eaeea00
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1786636000.0
updated_at: 1786636000.0
---

`hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M` is Qwen's Qwen3.8-27B (released 2026-08, Apache 2.0) —
dense 27B, hybrid Gated-DeltaNet/Gated-Attention layers, 262K native context (extensible to 1M
via YaRN), unsloth GGUF quant (~17GB). `config/backends.yaml` registers it in `group: coding`
with `supports_tools: true`, verified via a direct `/api/chat` tool-call probe (clean structured
`tool_calls`, correctly typed arguments) rather than inferred from the model card. `config/portal.yaml`
gives it the `bench-qwen38-27b` workspace `model_hint`. Also live in the coding IDE lane directly
via `config/personas/qwen38coder.yaml` (`workspace_model: auto-coding`, `model_pin` to this exact
tag, `ide_expose: true`) for real-work evaluation instead of a synthetic bench sweep — TPS bench
measured 6.8 t/s (dense 27B, well below any web-lane floor, but IDE lanes accept below-floor speed
if quality holds up). Model card claims (unverified in-fleet): SWE-bench Pro 61.7%, Terminal-Bench
73.0%, OSWorld-Verified 84.3%, GPQA Diamond 89.2%, LiveCodeBench 90.3%. PROMOTE_POLICY=confirm.

## Why

Added live to `auto-coding`'s IDE lane rather than run the full `bench_repair` 10-problem sweep
first — at 6.8 t/s the sweep's 70 samples would have taken 2-4+ hours, and the operator preferred
real usage data over a long synthetic run for this intake. The `model_pin` + `ide_expose: true`
combination mirrors the existing `devstral_coder`/`glm_coder` (model_pin) and `agenticheavy`/
`pentestlead` (ide_expose) personas, giving this candidate its own selectable IDE picker slot
without disturbing `auto-coding`'s primary routing.
