---
id: unit-model-catalog-sylink-sylink-8b-ctx8k
kind: what
title: "MODEL_CATALOG \u2014 `sylink/sylink:8b-ctx8k`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: a23f47b3e687df1693600eeea5b4f3f381b9da20
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.658734
updated_at: 1784946220.658734
---

`sylink/sylink:8b-ctx8k` is the context-capped derivation of `sylink/sylink:8b` with `PARAMETER num_ctx 8192` baked into the tag. `config/backends.yaml` registers it under `group: security` (`ollama-security`) with `supports_tools: false`, inheriting the base model's no-native-tool-calling posture. Unlike the base tag, which `config/portal.yaml` references as the `model_hint` of the `bench-sylink-8b` and `bench-sylink` eval workspaces, the `-ctx8k` tag currently has no live `model_hint`; the auto-security `blueteam` variant points at `granite4.1:8b-ctx8k` instead. The tag is retained to satisfy backends.yaml and `config/MODEL_CATALOG.md` parity, enforced by `tests/unit/test_model_catalog_parity.py`, for a future workspace that wants the 8K-capped SYLink.

## Why

The `-ctx8k` tag is the rare case of a declared backend model with no production consumer: every workspace that would use SYLink at 8K context either retired the model from the lane or moved to `granite4.1:8b-ctx8k`. Grounding to the security-group entry and to the absence of a portal.yaml `model_hint` documents both that the tag is real and that nothing routes to it, so a future promotion is a deliberate decision rather than an assumption.
