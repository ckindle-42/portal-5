---
id: unit-model-catalog-meta-secalign-8b-q4-k-m-latest
kind: what
title: "MODEL_CATALOG \u2014 `meta-secalign-8b-q4_k_m:latest`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 0fec84d46a8898b1b5baf0508af1e25634b099af
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.62993
updated_at: 1784946220.62993
---

`meta-secalign-8b-q4_k_m:latest` is the explicit-`:latest`-tagged sibling of `meta-secalign-8b-q4_k_m`, added during the 2026-07-18 GATE-D ablation hint-validation fix when the untagged hint never resolved against `ollama list`'s tagged id. `config/backends.yaml` registers it in `group: general` with `supports_tools: false`; the security-group entry carries the untagged id instead. `config/portal.yaml` pins this exact `:latest` spelling as the `bench-meta-secalign-8b` workspace `model_hint`. Same weights as the base id; only the tag string differs, and the tag string is what hint validation and the bench workspace require.

## Why

This unit exists because the tag spelling is load-bearing: the untagged hint failed hint validation, so the `:latest` form is what `config/portal.yaml`'s bench workspace actually consumes. Grounding to the general-group registration (supports_tools false) and the bench `model_hint` shows why the suffixed id is registered at all — a routing fix, not a distinct model.
