---
id: unit-design-ollama-native-dispatch
kind: why
title: Ollama Native Dispatch and the Engine Contract Loop
sources:
- type: code
  path: portal/platform/inference/ollama_native.py
- type: code
  path: scripts/engine_contract_check.py
- type: code
  path: scripts/engine_autoupdate.py
- type: code
  path: scripts/omlx_seat_defaults.py
- type: code
  path: config/engine_contract.yaml
claims: []
confidence: high
tags:
- design
- ollama
- omlx
- sampling
created_at: 1790333591
updated_at: 1790333591
---

The pipeline speaks OpenAI end to end, but Ollama's OpenAI endpoint cannot carry the settings Portal configures (see P5-OLLAMA-V1-SAMPLING-001), so Ollama backends are answered from native `/api/chat` by `OllamaNativeTransport`, mounted on the shared httpx client in `router/lifespan.py`. It intercepts only POST `/v1/chat/completions` to a base URL the registry positively knows is an Ollama backend; oMLX, vLLM and every other URL pass through untouched. It translates the request (sampling from `options` and top-level, `max_tokens` -> `num_predict`, content parts split one message per part as `/v1` does, tool-call arguments to objects, `think` only for models whose `/api/show` capabilities include thinking) and returns the byte-for-byte `/v1` shape (`reasoning`, string tool arguments, `finish_reason: tool_calls`, trailing usage chunk). Model-lifecycle fields (`num_ctx`, `num_batch`, `keep_alive`) are deliberately not forwarded — `/v1` never delivered them and honouring them would change memory behaviour, not fix delivery.

Maintenance is mechanical because Ollama ships often and oMLX has major versions ahead: `scripts/engine_contract_check.py` proves, for the running version of each engine, that every sampling key and the think control change the model's output through production's own request builders (`_inject_ollama_options` / `_inject_omlx_options`), and that the adapter answers identically to `/v1`. `scripts/engine_autoupdate.py` (daily launchd job) re-runs it whenever a version changes and gates weekly engine updates on it, rolling back on failure. The WFE harness serves Ollama arms through the same `to_native_request` translation so a benchmark measures exactly what production serves. Clients that talk to oMLX directly (IDE paths) receive a seat's sampling through oMLX's per-model defaults, written by `scripts/omlx_seat_defaults.py` from `config/portal.yaml` when exactly one production seat maps to the model.

## Why

The rejected alternative was baking sampling into Ollama tags: it needs no request-path code, but it makes sampling a property of a shared tag (seats that share a tag conflict), turns every sampling change into a re-bake that drifts silently if missed, and still cannot deliver `think: true`. The adapter keeps `config/portal.yaml` the single source of truth; its exposure to Ollama changes is bounded by the contract loop rather than by hope.
