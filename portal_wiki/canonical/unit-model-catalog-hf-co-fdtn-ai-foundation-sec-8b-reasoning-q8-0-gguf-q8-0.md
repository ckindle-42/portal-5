---
id: unit-model-catalog-hf-co-fdtn-ai-foundation-sec-8b-reasoning-q8-0-gguf-q8-0
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 9c0a4efa9fea8836ee3466b206c01b042c59455f
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.63576
updated_at: 1784946220.63576
---

`hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0` is Cisco's Foundation-Sec-8B-Reasoning Q8_0 (~8.5GB, 128K ctx, Llama-3.1-8B cybersec continued-pretrain + reasoning, Apache 2.0, native `<think>`). `config/backends.yaml` registers it in the `reasoning` group only, with `supports_tools: false` — matching the documented 400 error on all tool probes from the 2026-06-21 Run A; it is not present in the security group. `config/portal.yaml` uses it as the `model_hint` for `bench-foundation-sec-8b-reasoning` (the GATE-D ablation's locked V2-trio Expert model) and as the `expert_model` for the `blueteam-council` and `blueteam-orchestrated` variants of `auto-security`, where the no-tools reasoning model renders analytical verdicts.

## Why

The doc body claimed it was "MOVED from security group to reasoning"; re-grounding confirms the move mechanically — `config/backends.yaml` has it only under `reasoning`, never under `security`. The `supports_tools: false` flag and the 400-error probe note are consistent with the config and its comments. `config/portal.yaml`'s use as blueteam `expert_model` and bench `model_hint` proves the analytical-serving role the doc asserted, grounding every claim in the two config files.
