---
id: unit-model-catalog-hf-co-gaston-parravicini-lfm2-5-8b-a1b-uncensored-gaston-gguf-q4-k-m
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/gaston-parravicini/LFM2.5-8B-A1B-Uncensored-Gaston-GGUF:Q4_K_M`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 1896bb7da29dd96ff280b8ffb495519d507070ee
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.643104
updated_at: 1784946220.643104
---

`hf.co/gaston-parravicini/LFM2.5-8B-A1B-Uncensored-Gaston-GGUF:Q4_K_M` is the gaston-parravicini imatrix Q4_K_M (~5GB) of the abliterated LiquidAI/LFM2.5-8B-A1B base, a head-to-head candidate against production `lfm2.5:8b` for creative/music/agentic lanes. `config/backends.yaml` registers it in the `general` and `creative` groups, both with `supports_tools: false`; the creative entry confirms the no-tool posture — audit-tools 2026-06-18 recorded an empty content response, meaning the abliteration broke the tool template that production `lfm2.5:8b` still carries. `config/portal.yaml` selects it as the `model_hint` for `bench-lfm25-8b-uncensored`, while the `-ctx8k` derived tag is the `model_hint` for `auto-extract-uncensored`, the extraction/summarization lane that is explicit-select rather than a default.

## Why

The doc body's claim that abliteration broke the tool template is now pinned to `config/backends.yaml`, where both the `general` and `creative` entries carry `supports_tools: false`. `config/portal.yaml` records the serving role: base id to the bench lane, `-ctx8k` tag to `auto-extract-uncensored`. The head-to-head-vs-production framing survives because the bench workspace description states it, and the extraction-lane facts come straight from its description.
