---
id: unit-model-catalog-hf-co-mradermacher-qwen3-5-9b-claude-4-6-highiq-thinking-heretic-uncensored-gguf-q4-k-m
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/mradermacher/Qwen3.5-9B-Claude-4.6-HighIQ-THINKING-HERETIC-UNCENSORED-GGUF:Q4_K_M`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 3cdc95603cf1faa41ddd64aa3eaad1ec45a113ce
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.640563
updated_at: 1784946220.640563
---

`hf.co/mradermacher/Qwen3.5-9B-Claude-4.6-HighIQ-THINKING-HERETIC-UNCENSORED-GGUF:Q4_K_M` is registered in `config/backends.yaml` twice, under the `general` group and under the `vision` group, and both entries set `supports_tools: false`. The vision entry's comment records that it is a thinking model, not an agentic one, and the first uncensored vision option in the fleet. `config/portal.yaml` binds it as the `bench-qwen35-9b-heretic-vision` workspace `model_hint`, whose description preserves the ~5.6GB Q4_K_M footprint, the trohrbaugh heretic-v2 abliteration (KLD 0.079, 6/100 refusals), and the 262K-to-1M context via YaRN. The Claude-4.6 distill label is treated as unverifiable-provenance marketing; both config files mark the intake as a V11 bench-only candidate with PROMOTE_POLICY=confirm.

## Why

The dual registration under `general` and `vision` with `supports_tools: false` is asserted directly by `config/backends.yaml`, and `config/portal.yaml` binds it to the `bench-qwen35-9b-heretic-vision` bench workspace. The institutional knowledge about the heretic-v2 abliteration quality and the fleet's first uncensored vision status is preserved because it explains why the model is registered across two groups yet deliberately kept out of tool-calling lanes.
