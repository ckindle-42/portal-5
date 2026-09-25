---
id: unit-known-limitations-ollama-v1-sampling-drop
kind: what
title: Ollama /v1 Silently Dropped Workspace Sampling (Resolved; residual limits)
sources:
- type: code
  path: portal/platform/inference/ollama_native.py
- type: code
  path: portal/platform/inference/router/lifespan.py
- type: code
  path: portal/platform/inference/router/validation.py
- type: code
  path: scripts/engine_contract_check.py
claims: []
confidence: high
tags:
- known-limitations
- ollama
- resolved
- sampling
created_at: 1790333591
updated_at: 1790370000
---

- **ID**: P5-OLLAMA-V1-SAMPLING-001
- **Status**: RESOLVED 2026-09-25 — Ollama backends are served from native `/api/chat` by `OllamaNativeTransport`; residual limits below remain.
- **Description**: The pipeline sent each workspace's sampling inside `options`, which Ollama's `/v1/chat/completions` ignores entirely; `/v1` also has no field for `top_k`, `min_p` or `repeat_penalty`, and forces `temperature`/`top_p` to 1.0 when a request omits them (`FromChatRequest` in Ollama's `openai.go`). Every Ollama-served workspace therefore ran at temperature 1.0 / top_p 1.0 with the tag's baked top_k/min_p/repeat_penalty, never at its `config/portal.yaml` sampling; a `think: true` was dropped as well. Upstream declined to add the fields (ollama#11325, closed not-planned). Measured 2026-09-25 on 0.34.2 with extreme values (top_k=1 / min_p=1 collapse three seeds to one output only when honoured).
- **Fix**: an httpx transport on the pipeline's shared client answers `/v1/chat/completions` for registered Ollama backends from `/api/chat` and returns the exact `/v1` response shape (parity-verified on text, tools, tool-result turns, non-thinking models and image parts — content, tool calls and prompt tokens identical). `scripts/engine_contract_check.py` re-proves delivery of every key through production's own request builders on each engine version change.
- **Residual limits**: (1) `presence_penalty` reaches Ollama but its sampler applies nothing — seats declaring it on Ollama are flagged `presence_ignored_by_ollama` by the settings auditor; since 2026-09-25 the production Ollama seats whose card asks for presence 1.5 carry `repeat_penalty: 1.05` instead (a working substitute, calibrated in `docs/TASK_SEAT_SAMPLING_AB_V1.md`); (2) Ollama has no `tool_choice` field: `"none"` and a named function are expressed through the offered tools list (since 2026-09-25), but `tool_choice=required` forcing has never applied on Ollama seats — the single-tool schema is what narrows the call; (3) `keep_alive` is deliberately NOT forwarded: `/v1` never delivered it, so every model has always been released on Ollama's server default, and turning on the pipeline's `-1` default would pin models oMLX cannot reclaim — an operator decision, not a bug fix.

## Why

The failure returned HTTP 200 on every request, so nothing in the stack could see it; only a behavioural probe can. Recording the residual limits keeps the three keys that still do not behave as configured from being mistaken for a regression of the fix.
