---
id: unit-model-catalog-hf-co-deepreinforce-ai-ornith-1-0-35b-gguf-q4-k-m-ctx64k
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/deepreinforce-ai/Ornith-1.0-35B-GGUF:Q4_K_M-ctx64k`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 41df61e0a6102275a700700e9765972f1508c4c5
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.648853
updated_at: 1784946220.648853
---

`hf.co/deepreinforce-ai/Ornith-1.0-35B-GGUF:Q4_K_M-ctx64k` is the 64K-context derived tag of Ornith-1.0-35B. `config/backends.yaml` registers the `-ctx64k` tag in the `coding` group with `supports_tools: true`; the base `Q4_K_M` id appears in both `general` (false) and `coding` (true), so the capped tag keeps the coding-group tool capability while extending the window. `config/portal.yaml` selects this exact tag as the `model_hint` for the `ornith` variant of `auto-coding`, whose description records the 2026-06-30 promotion from `bench-ornith-35b` on strong tool-chain and SWE-handoff probe markers. `PARAMETER num_ctx 65536` is baked in via `portal models apply-params` because Ollama ignores request-time `options.num_ctx`. The base id remains `bench-ornith-35b`'s `model_hint`.

## Why

The old body was the shared derived-tag template. Re-grounding distinguishes it with the tag's actual config footprint: `config/backends.yaml` places the `-ctx64k` id in `coding` (with its base split across `general`/`coding`), and `config/portal.yaml` shows the `ornith` variant of `auto-coding` consuming it as `model_hint`. The promotion and probe-marker facts are retained because the variant description records them; the template prose is replaced by config-derived specifics.
