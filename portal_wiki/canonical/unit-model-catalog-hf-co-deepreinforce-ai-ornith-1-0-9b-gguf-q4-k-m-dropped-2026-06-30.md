---
id: unit-model-catalog-hf-co-deepreinforce-ai-ornith-1-0-9b-gguf-q4-k-m-dropped-2026-06-30
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/deepreinforce-ai/Ornith-1.0-9B-GGUF:Q4_K_M` \u2014\
  \ DROPPED 2026-06-30"
sources:
- type: code
  path: tests/benchmarks/results/v10_candidates_20260629T202251Z.json
last_generated_commit: ba66a30a47f104a137e20da5d5a3e3e9cc0b3360
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.615906
updated_at: 1784946220.615906
---

Ornith-1.0-9B Q4_K_M was evaluated as a V10 coding candidate under the
`bench-ornith-9b` workspace. The `TASK_MODEL_EVAL_V10_CANDIDATES` record in
`tests/benchmarks/results/v10_candidates_20260629T202251Z.json` carries its tool-chain
probe run, where it scored above the baseline floor on its probe markers for the
ImportError-diagnosis scenario. It was dropped on 2026-06-30: the same batch kept the
35B sibling, and `bench-ornith-35b` was promoted from the V10 candidate eval per the
workspace entry in `config/portal.yaml`. The 9B model id appears nowhere in
`config/backends.yaml` or `config/portal.yaml` today — grep finds only the 35B survivor —
so the dropped record is consistent with the live registry.

## Why

The old body stated a model size and marker counts that no source file determines and
a keep-the-35B-sibling verdict that was only lore. The scoring record pins the
evaluation, and config/portal.yaml pins the drop: the 35B sibling was promoted from
the same V10 eval on the same date while the 9B appears nowhere in the registry today.
The figure-free phrasing keeps the body truthful as the registry evolves rather than
embalming a stale score.
