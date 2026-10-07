---
id: unit-ollama-native-passthrough
kind: mixed
title: "Native Ollama passthrough — authenticated, load-guarded inference"
sources:
- type: code
  path: portal/platform/inference/router/ollama_passthrough.py
- type: code
  path: portal/platform/inference/router/app.py
- type: code
  path: portal/platform/inference/router/lifespan.py
- type: code
  path: portal/platform/inference/load_guard.py
- type: code
  path: portal/platform/inference/router/routing.py
- type: code
  path: portal/platform/inference/tool_preselect/preselector.py
- type: code
  path: portal/platform/inference/ollama_native.py
- type: code
  path: portal/platform/memory/graph_memory.py
- type: code
  path: portal/modules/research/tools/rag_multimodal.py
- type: code
  path: portal/modules/compliance/core/transport_dialects.py
- type: code
  path: portal/modules/compliance/core/reading_transport.py
- type: code
  path: portal/platform/wiki/adapters/portal_inference.py
- type: code
  path: config/ollama_direct_allowlist.yaml
- type: code
  path: scripts/validation/ollama_direct.py
- type: code
  path: deploy/portal-5/docker-compose.yml
- type: code
  path: .env.example
- type: code
  path: tests/unit/test_ollama_passthrough.py
- type: code
  path: tests/unit/test_ollama_direct_allowlist.py
- type: code
  path: scripts/memory_safety_watch.py
- type: code
  path: tests/unit/test_memory_safety_watch.py
claims: []
confidence: high
tags:
- capability
- inference
- memory-safety
---

# Native Ollama passthrough — authenticated, load-guarded inference

The pipeline exposes `POST /ollama/api/chat`, `/generate`, and `/embed`, plus
read-only `/ollama/api/ps`, `/tags`, and `/show`. Every route requires the
pipeline bearer key. The proxy selects the first healthy Ollama backend from
`BackendRegistry`, forwards native request bytes unchanged with a dedicated
HTTPX client, and streams the upstream status, headers, and body back without
the OpenAI translation in `OllamaNativeTransport`.

Inference routes call `LoadGuard.admit` before sending, track the model as busy
while the response is being read, and release both tracking and any cold-load
lock on completion or stream close. A guard refusal is returned as HTTP 507 in
Ollama's `{"error": "..."}` shape. This preserves `think`, `format`, `images`,
`options`, `keep_alive`, and `message.thinking` for native-protocol clients.

The memory extractor, RAG page transcription, compliance `ollama-native`
rollback, and wiki seeding adapter default to this route and send
`PIPELINE_API_KEY`. Tool preselection and startup warmup stay inside the
pipeline process and call `LoadGuard.admit` directly. The pinned intent-router
call is only tracked as busy (`LoadGuard.begin`), never admitted: it is resident,
and an admission check would put an `/api/ps` round-trip inside every routing
deadline. The AST-based
`validate_system` check scans runtime `portal/**` code and requires a reasoned
entry in `config/ollama_direct_allowlist.yaml` for operator probes, gated
engine diagnostics, or guarded pipeline internals that still construct native
requests. Multi-model live checks run under `scripts/memory_safety_watch.py`,
which samples host swap, memory pressure, and oMLX headroom every two seconds.
It trips on critical kernel memory pressure, or on low free swap only while free
memory is also low (macOS grows swap in 1 GiB files on demand, so low free swap
alone is routine). On a trip it stops test clients, unloads non-router Ollama
and idle oMLX models, and writes an evidence log.

## Why

On 2026-10-07 oMLX and Ollama loaded 27B-class models at once into one unified
memory pool and the Mac was watchdog-reset. Callers that reached Ollama directly
never met the host-wide load guard. Routing native callers through the pipeline
over HTTP puts every inference load behind one admission point, while MCP
modules keep zero imports from `portal.platform.inference` (Rule 3). The
rejected alternative was sending these callers through the OpenAI `/v1`
surface: it would drop native fields (`think`, `format`, `message.thinking`,
request-time `num_ctx`) that compliance readings and memory extraction rely on.
