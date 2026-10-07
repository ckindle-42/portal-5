---
id: unit-design-client-disconnect-cancellation
kind: mixed
title: "Client disconnect cancels inference work end to end"
sources:
- type: code
  path: portal/platform/inference/router/disconnect.py
- type: code
  path: portal/platform/inference/router/correlation.py
- type: code
  path: portal/platform/inference/router/handlers.py
- type: code
  path: portal/platform/inference/router/ollama_passthrough.py
- type: code
  path: portal/platform/inference/router/metrics.py
- type: code
  path: portal/platform/inference/streaming_client.py
- type: code
  path: portal/platform/inference/load_guard.py
- type: code
  path: portal/modules/compliance/core/cancellation.py
- type: code
  path: portal/modules/compliance/tools/compliance_mcp.py
- type: code
  path: portal/modules/compliance/core/council.py
- type: code
  path: portal/modules/compliance/core/sweep.py
- type: code
  path: portal/modules/compliance/core/reading_transport.py
- type: code
  path: portal/modules/compliance/core/transport_dialects.py
- type: code
  path: tests/unit/test_cancellation_w3.py
- type: code
  path: reports/host_memory_safety/W3.md
claims: []
confidence: high
tags:
- design
- inference
- memory-safety
---

# Client disconnect cancels inference work end to end

A client that gives up stops the work it started.

* **Pipeline, non-streaming.** `/v1/chat/completions` (council included) and the
  native `/ollama/api/*` passthrough run their pre-response work through
  `disconnect.cancel_on_disconnect`. It polls `request.is_disconnected()` every
  0.5 s and cancels the task when the client leaves. The cancel aborts the
  upstream httpx request, which closes the engine connection. The response is
  499, and `portal5_client_disconnect_cancel_total{path}` counts it.
* **Pipeline, streaming.** Starlette's `StreamingResponse` cancels the generator
  on disconnect, and the generator's cleanup closes the upstream stream. This
  needs no watcher.
* **Middleware.** `CorrelationIdMiddleware` is pure ASGI. As a
  `BaseHTTPMiddleware` it hid the disconnect from `is_disconnected()`, so no
  handler behind it could see its client leave.
* **Engines.** Ollama stops generating when the connection closes (`cancel task`;
  logged as 499 or 500). oMLX drops `active_requests` within a second. Models
  stay resident (`keep_alive` unchanged).
* **Load guard.** A request cancelled during admission releases the host-wide
  cold-load lock.
* **Compliance MCP.** `invoke_tool` binds a `CancelToken` (a `ContextVar`) and
  runs the tool under a copy of that context. On disconnect it cancels the
  token. `stream_chat_turn(should_cancel=...)` checks it on every line, and a
  watcher thread shuts the socket down so a read blocked in prefill wakes. The
  urllib `_post` path checks before each call, the council between seats, and
  the sweep between readings (each worker gets the caller's context).
  `TurnCancelled` is a `BaseException`, so the loops' `except Exception`
  non-vote paths cannot swallow it. The tool returns 499 with a `cancelled`
  receipt, never a partial verdict.

## Why

On 2026-10-07, 90 s client timeouts left compliance council seats running
server-side, requests piled up, and memory ran out. Without cancellation, every
abandoned request keeps a model busy and resident and holds the guard's busy
count, so the load guard sees memory that will never come free.
