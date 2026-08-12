---
id: unit-model-catalog-hf-co-mradermacher-cybersecqwen-4b-gguf-q4-k-m-dropped-tool-call-blocker-fixed-2026-07-04-detection-quality-inconclusive-not-adopted
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/mradermacher/CyberSecQwen-4B-GGUF:Q4_K_M` \u2014\
  \ DROPPED (tool-call blocker fixed 2026-07-04; detection quality inconclusive, not\
  \ adopted)"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 640a004e4a83811639544dfada51fcd1268b0688
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.62912
updated_at: 1784946220.62912
---

`hf.co/mradermacher/CyberSecQwen-4B-GGUF:Q4_K_M` is the mradermacher community quant (~2.5GB, Qwen3-4B base, Apache-2.0) of the athena129/CyberSecQwen-4B blue-defender candidate. `config/backends.yaml` registers it in the `security` group with `supports_tools: false`; the inline comment records that Ollama itself hard-errors "does not support tools" for this tag — no tool-calling template at all — and points to the `cybersecqwen-4b-toolfix` derivative (also in `security`, `supports_tools: true`) as the usable variant. `config/portal.yaml` selects the base tag as the `model_hint` for `bench-cybersecqwen-4b`, a GATE-D ablation Expert-role candidate. The tool-call blocker was traced to the shipped ChatML template (no `{% if tools %}` block), not the model; a hand-authored toolfix Modelfile verified clean tool_calls, but the model was not adopted because real-scenario detection quality stayed inconclusive.

## Why

The doc narrative (dropped, blocker fixed 2026-07-04, not adopted) is preserved, but the config-resolvable facts are now pinned: `config/backends.yaml` proves the `security`-group registration, the `supports_tools: false` flag, and the existence of the `cybersecqwen-4b-toolfix` derivative it points to, while `config/portal.yaml`'s `bench-cybersecqwen-4b` records the Expert-role bench use. Re-grounding keeps the institutional findings and replaces doc-only assertions with file-backed ones.
