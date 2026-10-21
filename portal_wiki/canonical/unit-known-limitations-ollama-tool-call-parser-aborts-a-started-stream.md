---
id: unit-known-limitations-ollama-tool-call-parser-aborts-a-started-stream
kind: what
title: "KNOWN_LIMITATIONS — Ollama's tool-call parser aborts a started stream (ollama#18563)"
sources:
- type: code
  path: portal/platform/inference/router/streaming.py
- type: code
  path: portal/platform/inference/ollama_native.py
- type: code
  path: portal/platform/inference/router/non_streaming.py
claims: []
confidence: high
tags:
- docs
- ollama
- streaming
- known-limitations
created_at: 1792612030
updated_at: 1792612030
---

- **ID**: P5-OLLAMA-STREAM-ABORT-001
- **Status**: OPEN upstream (ollama#18563; fix PRs #18571 / #14915 unmerged as of v0.40.8-rc0). The Pipeline now contains the failure on its own side.
- **Description**: Ollama's `qwen3coder` parser (`model/parsers/qwen3coder.go`, "qwen tool call parsing failed") aborts on a malformed tool call, and `server/routes.go` writes `{"error": ...}` as an NDJSON line *inside* the already-started HTTP 200 body. The OpenAI-compat layer cannot represent it: the stream ends with its content deltas but no finish chunk and no `[DONE]`, and a client that requires a `finish_reason` (opencode's `@ai-sdk/openai-compatible`) reports "OpenAI Chat stream ended without finish_reason". `nemotron35-lightning:code` (`PARSER nemotron-3.5-nano`) and the `PARSER qwen3.5` seats (`kat-coder-35b:code`, `qwen3.6-35b-a3b:q3code`) all delegate to that parser, so the three share it. It is rare but client-fatal: one event in the 2026-10-20 incident, one other on the box since 2026-10-19, and it did not retrigger in 6 valid live probes.
- **What the Pipeline does now**: an `{"error": ...}` line seen after a stream has started — Ollama native NDJSON or an OpenAI `data: {"error": ...}` frame — closes the client stream well-formed: the message as assistant content, one `finish_reason: "stop"` chunk, then `data: [DONE]` (`router/streaming.py`, `ollama_native.native_stream_to_sse`). The hop is logged with the correlation id and counted as `portal_errors_total{error_type="backend_in_band_error"}`; it is not retried, and no non-streaming fallback answer is appended after the partial one. The non-streaming path raises the engine's error (HTTP 500 at the Ollama transport) instead of returning a 200 body with no `choices`.
- **Mitigation (external, unchanged)**: `nemotron35-lightning:code-fix` on thebrain lowers the trigger rate (temperature 1.0 → 0.6, `top_k 20`) but cannot prove elimination; `:code` itself is untouched.

## Why

The error is generated server-side after headers are sent, so no HTTP status can carry it — the only lever the Pipeline has is how it ends the stream it is already writing. Leaving it to the engine means an agent client treats a cancelled turn as a transport failure and aborts the step; terminating with content, a finish reason and `[DONE]` turns it into an answer the client can see and continue from, without inventing a retry the operator did not ask for.
