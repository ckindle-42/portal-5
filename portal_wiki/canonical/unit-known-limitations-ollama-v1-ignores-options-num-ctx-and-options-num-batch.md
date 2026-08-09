---
id: unit-known-limitations-ollama-v1-ignores-options-num-ctx-and-options-num-batch
kind: what
title: "KNOWN_LIMITATIONS \u2014 Ollama /v1 ignores options.num_ctx and options.num_batch"
sources:
- type: code
  path: portal/platform/inference/router/validation.py
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
- type: code
  path: portal/modules/security/core/blue_orchestrate.py
- type: code
  path: portal/modules/security/core/agentic_blue_eval.py
- type: code
  path: portal/modules/security/core/_sweep_driver.py
last_generated_commit: 925f52c4b7e7ec876ea24823d3a221c7f2f8f505
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.6741362
updated_at: 1785460800
---

- **ID**: P5-OLLAMA-OPTIONS-001
- **Description**: Ollama's OpenAI-compatible `/v1/chat/completions` endpoint ignores the `options` sub-object (VERIFY-1 probes, 2026-06). The pipeline still injects `options.num_ctx` (from each workspace's `context_limit`) and `options.num_batch` (fixed 2048) because a future Ollama version may honor them; `predict_limit` is mapped to top-level `max_tokens`, which IS honored. `_apply_workspace_settings` in `portal/platform/inference/router/validation.py` implements all three injections.
- **Consequence**: `context_limit` per workspace (e.g. `auto-coding: 16384`) is not enforced through `/v1` — it must be baked into the model's Modelfile or set via `OLLAMA_CONTEXT_LENGTH`. `num_batch` injection is likewise inert.
- **Mitigation proof**: Raw `granite4.1:30b` loaded at 131,072 tokens while `granite4.1:8b` loaded at the same default, so the security evaluation workspaces now use baked `granite4.1:30b-ctx16k` and `granite4.1:8b-ctx8k` tags (registered in `config/backends.yaml`; used by `portal/modules/security/core/blue_orchestrate.py`, `agentic_blue_eval.py`, and `_sweep_driver.py`). Ollama then reports contexts 16,384 and 8,192 respectively. This mitigates the operated workspaces but does not resolve the general `/v1` limitation.
- **Roadmap note**: evaluate `/api/chat` as the chat URL — it honors the Ollama-native parameter set but requires changing all payload/response shapes.

## Why

The `/v1` compatibility surface is convenient but drops the `options` object, so context and prefill tuning must travel through a channel the endpoint actually honors. Baking a context-limited tag per workspace is the pragmatic fix because it moves the constraint into the Modelfile where Ollama cannot ignore it, while the pipeline keeps injecting `options` for future compatibility rather than deleting a currently-inert but standards-shaped field.
