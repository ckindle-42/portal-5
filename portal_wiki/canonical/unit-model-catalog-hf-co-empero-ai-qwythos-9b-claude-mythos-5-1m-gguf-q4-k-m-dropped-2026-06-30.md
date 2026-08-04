---
id: unit-model-catalog-hf-co-empero-ai-qwythos-9b-claude-mythos-5-1m-gguf-q4-k-m-dropped-2026-06-30
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/empero-ai/Qwythos-9B-Claude-Mythos-5-1M-GGUF:Q4_K_M`\
  \ \u2014 DROPPED 2026-06-30"
sources:
- type: code
  path: tests/benchmarks/results/v10_candidates_20260629T194541Z.json
last_generated_commit: ba66a30a47f104a137e20da5d5a3e3e9cc0b3360
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.6361191
updated_at: 1784946220.6361191
---

Qwythos-9B Claude-Mythos-5-1M Q4_K_M was evaluated as a V10 candidate under the
`bench-qwythos-9b` workspace and dropped on 2026-06-30. The
`TASK_MODEL_EVAL_V10_CANDIDATES` record in
`tests/benchmarks/results/v10_candidates_20260629T194541Z.json` shows it scoring at
the floor on the long-context needle probe — its 1M-context headline bought nothing in
a 50KB needle hunt — and falling short on the uncensored-depth probe. On those two
probes it cleared no meaningful bar, and the drop verdict followed. The model id
appears in neither `config/backends.yaml` nor `config/portal.yaml`, matching the
dropped record.

## Why

The prior body asserted a model size, a dataset-provenance story, and precise marker
figures that the result file does not determine. The V10 probe record is the whole
grounding: bench-qwythos-9b hit the floor on its signature long-context needle probe,
which is the meaningful finding for a 1M-context model, and the registry today contains
no qwythos id. Keeping the needle-probe outcome in figure-free terms preserves the
verdict without pinning an unbindable score.
