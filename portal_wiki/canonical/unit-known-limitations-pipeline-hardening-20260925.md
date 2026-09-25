---
id: unit-known-limitations-pipeline-hardening-20260925
kind: what
title: Pipeline Request-Path Hardening (Resolved 2026-09-25)
sources:
- type: code
  path: portal/platform/inference/router/streaming.py
- type: code
  path: portal/platform/inference/router/non_streaming.py
- type: code
  path: portal/platform/inference/router/handlers.py
- type: code
  path: portal/platform/inference/router/anthropic_compat.py
- type: code
  path: portal/platform/inference/router/context_inject.py
- type: code
  path: portal/platform/inference/ollama_native.py
- type: code
  path: portal/platform/inference/tool_registry.py
- type: code
  path: tests/unit/test_pipeline_hardening.py
claims: []
confidence: high
tags:
- known-limitations
- pipeline
- resolved
- streaming
created_at: 1790370000
updated_at: 1790370000
---

- **ID**: P5-PIPELINE-HARDEN-001
- **Status**: RESOLVED 2026-09-25. Every item was reproduced against the live stack before the fix and re-verified live after it; `tests/unit/test_pipeline_hardening.py` and `tests/unit/test_ollama_native.py` pin each one.
- **Fallback discipline**: a failed request was resent to the same engine and model once per backend group fronting it, then served by an unrelated model (`backend.models[0]` of the last candidate — e.g. `auto-music` answered by Qwen3-Coder-30B), and a malformed request (HTTP 400/413/422) cascaded into an opaque 502. Now each `(engine URL, model)` pair is attempted once per request, a malformed request is returned to the client with the engine's message, a different model is substituted only when no healthy backend serves the hint at all, and a 502 names each attempt's failure. Ollama reports request-validation errors as 500 (`option "top_k" must be of type integer`), so those still cascade — but only across genuinely different engine/model pairs.
- **Streaming fallback**: a stream that failed after output reached the client was re-answered non-streaming and appended to the partial answer; an error-envelope match on the substring `"error"` could fire on content; a trailing `[DONE]` was forwarded ahead of the fallback answer. The fallback now runs only when nothing has been shown, errors are parsed, and one `[DONE]` ends every stream (the tool loop included — its reasoning fallback and empty-response notice used to follow `[DONE]`, invisible to OpenAI-SDK clients).
- **Reasoning display (review item C-1)**: every streamed `reasoning` delta was rewritten into `content`, so OWUI printed the chain of thought as the answer. Reasoning now passes through (OWUI renders it collapsed) and is promoted to content only when a turn ends with none — the non-streaming rule. A space-separated `"content": "` frame or a client tool call no longer triggers a false "empty response" notice.
- **Request shapes**: list-form `system` content (OpenAI content parts, sent by IDE clients) raised a 500 in every workspace with a system-prompt append, temporal context or memory injection. The native Ollama adapter 500'd on `stop` as a string and ignored `tool_choice: "none"` / a named function (now expressed through the offered tools), and dropped message fields on the final `done` chunk.
- **Anthropic `/v1/messages` (Claude Code)**: `x-api-key` auth — what `ANTHROPIC_API_KEY` sends, as `scripts/cc-local.sh` sets — was rejected with 401; streamed tool calls were dropped (`stop_reason: tool_use` with no `tool_use` block); parallel `tool_result` blocks kept only the last; images were dropped; the ASGI loopback buffered the whole reply (first byte at completion). The endpoint now calls `chat_completions` in-process and streams incrementally.
- **Chains**: chain hops were posted to the primary backend's URL with the hop's raw model id, so with the primary on oMLX every Ollama-tagged hop 404'd (the purple-team blue-team/detection/IR hops); a tool-using chain workspace (`auto-security::purpleteam-exec`) skipped its chain entirely when streaming. Hops now resolve their own backend, and the first hop of a tool-using chain runs through the tool loop.
- **Tools and memory**: an MCP rejecting a model's arguments (HTTP 400/422) tripped the tool's circuit breaker, locking the tool for every request — including the model's corrected retry — for 30 s to 1 h. OWUI's background task prompts (title, tags, follow-ups: `### Task:` + `<chat_history>`) were written back as user memories on `auto-daily` and recalled into later conversations; they are now neither written back nor given memory. The council synthesizer now receives the workspace's `think` setting. Memories already stored from task prompts are not removed by this fix.

#### Why

None of these failures surfaced as an error the stack could see: each returned HTTP 200, a plausible answer from the wrong model, or a generic 502. They were found by tracing the request path and driving every entry shape (OWUI, OpenAI SDK, Anthropic SDK; streaming and not; Ollama and oMLX) through the live pipeline, which is the check to repeat after changes to the router.
