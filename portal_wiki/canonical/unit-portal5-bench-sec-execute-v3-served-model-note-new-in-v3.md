---
id: unit-portal5-bench-sec-execute-v3-served-model-note-new-in-v3
kind: what
title: "PORTAL5_BENCH_SEC_EXECUTE_V3 \u2014 Served-model note (new in V3)"
sources:
- type: code
  path: scripts/execute_preflight.py
- type: code
  path: portal/platform/inference/router/handlers.py
- type: code
  path: config/personas/glm_coder.yaml
last_generated_commit: ca0f99d64c0644df1d5fc30674b6c476fceb1a42
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.7091782
updated_at: 1784946220.7091782
---

Persona-level model pins (`model_pin`) are consumed by the pipeline, not the
bench: `portal/platform/inference/router/handlers.py` Phase 4c applies a
persona's `model_pin` through `_resolve_model_override` (bounded to the
`config/backends.yaml` model catalog) so a persona is served the model its
identity claims. Because the bench forwards workspace strings as the pipeline
`model` field, a run that qualifies a *persona* rather than a bare workspace is
only meaningful when that persona is served its pinned model. `scripts/execute_preflight.py`
prints every persona with a `model_pin` (slug → pin) under its "model_pin
personas" header; cross-check any persona appearing in your run against that
live list before trusting its capability score. The currently pinned set is
coding/vision/reasoning personas (for example `glm_coder`, `gemma_vision`,
`magistralstrategist`); no security-specific persona currently carries a pin, so
the original doc's "two security-adjacent personas" phrasing is stale.

## Why

A security persona benched on the wrong model produces a capability number that
means nothing, so the pin check is not cosmetic. Re-grounding replaces the
doc's unverifiable "two security-adjacent personas" claim with the preflight's
live enumeration, which is the only ground truth that stays correct as pins move
between personas over time.
