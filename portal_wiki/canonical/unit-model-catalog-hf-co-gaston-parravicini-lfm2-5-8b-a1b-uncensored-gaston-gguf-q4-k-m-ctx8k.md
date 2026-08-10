---
id: unit-model-catalog-hf-co-gaston-parravicini-lfm2-5-8b-a1b-uncensored-gaston-gguf-q4-k-m-ctx8k
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/gaston-parravicini/LFM2.5-8B-A1B-Uncensored-Gaston-GGUF:Q4_K_M-ctx8k`"
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
created_at: 1784946220.64936
updated_at: 1784946220.64936
---

`hf.co/gaston-parravicini/LFM2.5-8B-A1B-Uncensored-Gaston-GGUF:Q4_K_M-ctx8k` is the 8K-context derived tag of the abliterated LFM2.5-8B-A1B Uncensored model. `config/backends.yaml` registers it in the `creative` group only, with `supports_tools: false` — the same value as its base tag in both `general` and `creative`. `config/portal.yaml` uses this exact tag as the `model_hint` for `auto-extract-uncensored`, the entity/data-extraction and summarization workspace whose description notes the EX-01 5/5 bench pass and the explicit `tools=false` posture; it is explicit-select, not a default. `PARAMETER num_ctx 8192` is baked in via `portal models apply-params` because Ollama ignores request-time `options.num_ctx`. The base id, by contrast, routes to `bench-lfm25-8b-uncensored`.

## Why

The prior body was the shared ctx-cap placeholder. Re-grounding distinguishes this tag by its config reality: `config/backends.yaml` gives it a `creative`-only registration at `supports_tools: false`, and `config/portal.yaml` shows `auto-extract-uncensored` as its sole `model_hint` consumer. The extraction-lane details (EX-01 bench pass, tools=false, explicit-select) are lifted directly from that workspace's description, and the base-vs-derived `model_hint` split is verified in portal.yaml.
