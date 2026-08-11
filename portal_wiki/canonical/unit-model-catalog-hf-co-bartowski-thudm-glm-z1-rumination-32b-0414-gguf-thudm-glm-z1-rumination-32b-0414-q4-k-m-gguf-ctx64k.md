---
id: unit-model-catalog-hf-co-bartowski-thudm-glm-z1-rumination-32b-0414-gguf-thudm-glm-z1-rumination-32b-0414-q4-k-m-gguf-ctx64k
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/bartowski/THUDM_GLM-Z1-Rumination-32B-0414-GGUF:THUDM_GLM-Z1-Rumination-32B-0414-Q4_K_M.gguf-ctx64k`"
sources:
- type: code
  path: config/backends.yaml
last_generated_commit: d19bcd41d50c690918807eab095f1f738f9798d5
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.647352
updated_at: 1784946220.647352
---

`hf.co/bartowski/THUDM_GLM-Z1-Rumination-32B-0414-GGUF:THUDM_GLM-Z1-Rumination-32B-0414-Q4_K_M.gguf-ctx64k` is the 64K-context derived tag of GLM-Z1-Rumination-32B. `config/backends.yaml` registers it in the `coding` and `reasoning` groups — notably absent from `general`, where the base id does appear — with `supports_tools: false` in both. Because this unit is `in_portal: false`, `config/portal.yaml` carries no `model_hint` for it: no production or bench workspace selects the capped tag directly. `PARAMETER num_ctx 65536` is baked in via `portal models apply-params` because Ollama ignores request-time `options.num_ctx`; the derived tag is what would make a 64K window reachable, mirroring the base model's context-cap pattern. It exists to satisfy backends.yaml/MODEL_CATALOG parity (test_model_catalog_parity.py).

## Why

The old body was the generic derived-tag template copied across the ctx-family units. Re-grounding distinguishes this one by its actual config footprint: `config/backends.yaml` places it in `coding` and `reasoning` only (no `general` entry), both `supports_tools: false`, and the mapping's `in_portal: false` means `config/portal.yaml` never references it. Those are the config-determined facts; the rest of the template prose was identical placeholder text that the rewrite replaces.
