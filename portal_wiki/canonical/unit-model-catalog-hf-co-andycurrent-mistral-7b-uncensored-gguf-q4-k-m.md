---
id: unit-model-catalog-hf-co-andycurrent-mistral-7b-uncensored-gguf-q4-k-m
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/Andycurrent/Mistral-7B-Uncensored-GGUF:Q4_K_M`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 10c7734f3f87df5a9d525bb5c1f3970c96a73a91
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.597922
updated_at: 1784946220.597922
---

`hf.co/Andycurrent/Mistral-7B-Uncensored-GGUF:Q4_K_M` (~4.4GB, Andycurrent GGUF of the luvGPT base, Mistral-7B lineage) is a V13-A candidate intake, LINEAGE-DIVERSITY play for the Nano/Micro tier. `config/backends.yaml` declares it in the `general` group only, with `supports_tools: false` — the comment records the Step 1A preflight `/api/chat` probe that returned "does not support tools" because the model template lacks a `.Tools` declaration. `config/portal.yaml` selects it as the `model_hint` for `bench-mistral7b-uncensored`, whose description sets `tools: []` accordingly and keeps it on the bench lane. Mistral is not otherwise represented in the fleet, the same diversity-rationale class as `lfm2.5:8b`.

## Why

The doc body claimed the `supports_tools: false` result from a live probe; re-grounding pins it to the `config/backends.yaml` comment that records that exact probe and to the `config/portal.yaml` bench workspace that codifies `tools: []`. The lineage-diversity rationale survives because `bench-mistral7b-uncensored` states it. Every checkable claim now resolves to a config file instead of a doc paragraph.
