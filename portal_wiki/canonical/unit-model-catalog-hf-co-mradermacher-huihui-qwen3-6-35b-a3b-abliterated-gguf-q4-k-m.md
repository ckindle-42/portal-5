---
id: unit-model-catalog-hf-co-mradermacher-huihui-qwen3-6-35b-a3b-abliterated-gguf-q4-k-m
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/mradermacher/Huihui-Qwen3.6-35B-A3B-abliterated-GGUF:Q4_K_M`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 63cbca4c591d2d00f1cc9e3101ffa91f84a9a4a0
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.606283
updated_at: 1784946220.606283
---

`hf.co/mradermacher/Huihui-Qwen3.6-35B-A3B-abliterated-GGUF:Q4_K_M` is the mradermacher Q4_K_M (~20GB, MoE 3B active) of the huihui-ai abliteration of Qwen3.6-35B-A3B — a speed play leveraging 3B active parameters for fast decode. `config/backends.yaml` registers it in the `general` group only, with `supports_tools: false`. `config/portal.yaml` selects it as the `model_hint` for `bench-huihui-qwen36-35b-a3b`, whose description retains the vanch007 origin (the deleted HF repo this moved from; mradermacher hosts the same base as a confirmed Q4_K_M) and frames the lane as a speed comparison against `bench-huihui-qwen36-27b`. The model is bench-only; no production workspace pins it.

## Why

The doc body asserted the vanch007→mradermacher rehost; `config/portal.yaml`'s `bench-huihui-qwen36-35b-a3b` description still carries the vanch007 label while the `model_hint` uses the mradermacher id, corroborating the move. Re-grounding pins the `general`-group registration and `supports_tools: false` in `config/backends.yaml` and the bench-lane framing in `config/portal.yaml`. The 3B-active speed-play rationale and repo-history are kept because the bench description records them.
