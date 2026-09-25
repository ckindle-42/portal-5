---
id: unit-model-catalog-hf-co-gaston-parravicini-lfm2-5-8b-a1b-uncensored-gaston-gguf-q4-k-m
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/gaston-parravicini/LFM2.5-8B-A1B-Uncensored-Gaston-GGUF:Q4_K_M`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.643104
updated_at: 1784946220.643104
---
`hf.co/gaston-parravicini/LFM2.5-8B-A1B-Uncensored-Gaston-GGUF:Q4_K_M` is the gaston-parravicini imatrix Q4_K_M (~5GB) of the abliterated LiquidAI/LFM2.5-8B-A1B base, a head-to-head candidate against production `lfm2.5:8b` for creative/music/agentic lanes. `config/backends.yaml` lists it with `supports_tools: true` in every group (verified 2026-09-25 by a neutral native tool-call probe — sibling -ctx8k tag: 3/3 single-call plus a clean tool-result turn; the 2026-06-18 empty-content result did not reproduce); the router reads one flag per model id, last entry wins, so a per-group split never took effect. `config/portal.yaml` selects it as the `model_hint` for `bench-lfm25-8b-uncensored`, while the `-ctx8k` derived tag is the `model_hint` for `auto-extract-uncensored`, the extraction/summarization lane that is explicit-select rather than a default.

## Why

The earlier claim that abliteration broke the tool template (an empty-content result on 2026-06-18) did not reproduce on 2026-09-25: the `-ctx8k` tag called tools 3/3 and completed a tool-result turn, so both entries are now `supports_tools: true`. `config/portal.yaml` records the serving role: base id to the bench lane, `-ctx8k` tag to `auto-extract-uncensored`. The head-to-head-vs-production framing survives because the bench workspace description states it, and the extraction-lane facts come straight from its description.
