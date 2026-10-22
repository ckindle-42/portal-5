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
  path: portal/platform/inference/router/no_answer.py
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
updated_at: 1792684036
---

- **ID**: P5-PIPELINE-HARDEN-001
- **Status**: RESOLVED 2026-09-25. Every item was reproduced against the live stack before the fix and re-verified live after it; `tests/unit/test_pipeline_hardening.py` and `tests/unit/test_ollama_native.py` pin each one. Extended 2026-10-22: a chat-UI audience is now answered in words where a program still gets its status (`portal/platform/inference/router/no_answer.py`, `tests/unit/test_no_answer.py`), and streaming recovers from engine capacity the way non-streaming does (`tests/unit/test_stream_parity.py`).
- **Fallback discipline**: a failed request was resent to the same engine and model once per backend group fronting it, then served by an unrelated model (`backend.models[0]` of the last candidate — e.g. `auto-music` answered by Qwen3-Coder-30B), and a malformed request (HTTP 400/413/422) cascaded into an opaque 502. Now each `(engine URL, model)` pair is attempted once per request, a malformed request is returned to the client with the engine's message, a different model is substituted only when no healthy backend serves the hint at all, and a 502 names each attempt's failure. Ollama reports request-validation errors as 500 (`option "top_k" must be of type integer`), so those still cascade — but only across genuinely different engine/model pairs.
- **Streaming fallback**: a stream that failed after output reached the client was re-answered non-streaming and appended to the partial answer; an error-envelope match on the substring `"error"` could fire on content; a trailing `[DONE]` was forwarded ahead of the fallback answer. The fallback now runs only when nothing has been shown, errors are parsed, and one `[DONE]` ends every stream (the tool loop included — its reasoning fallback and empty-response notice used to follow `[DONE]`, invisible to OpenAI-SDK clients).
- **Reasoning display (review item C-1)**: every streamed `reasoning` delta was rewritten into `content`, so OWUI printed the chain of thought as the answer. Reasoning now passes through (OWUI renders it collapsed) and is promoted to content only when a turn ends with none — the non-streaming rule. A space-separated `"content": "` frame or a client tool call no longer triggers a false "empty response" notice.
- **Request shapes**: list-form `system` content (OpenAI content parts, sent by IDE clients) raised a 500 in every workspace with a system-prompt append, temporal context or memory injection. The native Ollama adapter 500'd on `stop` as a string and ignored `tool_choice: "none"` / a named function (now expressed through the offered tools), and dropped message fields on the final `done` chunk.
- **Anthropic `/v1/messages` (Claude Code)**: `x-api-key` auth — what `ANTHROPIC_API_KEY` sends, as `scripts/cc-local.sh` sets — was rejected with 401; streamed tool calls were dropped (`stop_reason: tool_use` with no `tool_use` block); parallel `tool_result` blocks kept only the last; images were dropped; the ASGI loopback buffered the whole reply (first byte at completion). The endpoint now calls `chat_completions` in-process and streams incrementally.
- **Chains**: chain hops were posted to the primary backend's URL with the hop's raw model id, so with the primary on oMLX every Ollama-tagged hop 404'd (the purple-team blue-team/detection/IR hops); a tool-using chain workspace (`auto-security::purpleteam-exec`) skipped its chain entirely when streaming. Hops now resolve their own backend, and the first hop of a tool-using chain runs through the tool loop.
- **Chain settings (2026-10-22)**: hops after the first dropped the workspace's per-backend output cap, think setting, and sampling. `resolve_hop_target` removed engine-specific keys when the hop's URL differed from the primary and did not rebuild them, so a later hop ran without `max_tokens` / `predict_limit`, `think`, and the sampling keys. The auto-security `purpleteam-deep` chain took about 500 s because of it. Merged in `be56ac40` (fix `938f3d2c`): streaming and non-streaming hops both call `resolve_hop_target`, which drops those engine-specific keys and reapplies the workspace settings for the destination backend through `_inject_ollama_options` or `_inject_omlx_options`. That reapply includes `thinking_budget` (oMLX top-level field; Ollama only as a card-documented think level). The 2026-09-25 routing fix is unchanged.
- **Tools and memory**: an MCP rejecting a model's arguments (HTTP 400/422) tripped the tool's circuit breaker, locking the tool for every request — including the model's corrected retry — for 30 s to 1 h. OWUI's background task prompts (title, tags, follow-ups: `### Task:` + `<chat_history>`) were written back as user memories on `auto-daily` and recalled into later conversations; they are now neither written back nor given memory. The council synthesizer now receives the workspace's `think` setting. Memories already stored from task prompts are not removed by this fix.
- **No dead ends for chat (2026-10-22)**: the statuses above still reached a program that can retry — and a bare error to a human reading the turn in Open WebUI. Every give-up path (non-streaming all-failed and capacity refusal, streaming single-candidate 507/5xx, tool-loop 507, fallback exhausted, chain last hop) now ends, for a chat-UI audience, in a well-formed assistant reply naming the model, why it could not be served, and a workspace whose model is loaded now — with no model substituted for the pinned one. API/harness clients keep the same status codes; the audience is Open WebUI's aiohttp user agent, the `X-OpenWebUI-*` headers, or the `X-Portal-Client` override, and every such turn is counted in `portal5_no_answer_total` by workspace, reason, audience and path. Streaming and non-streaming recover from an oMLX capacity refusal the same way — one helper frees idle Ollama residents and retries, used by the tool loop, the plain stream and the fallback driver — and the non-streamed cascade protects the model it failed over from.

#### Why

None of these failures surfaced as an error the stack could see: each returned HTTP 200, a plausible answer from the wrong model, or a generic 502. They were found by tracing the request path and driving every entry shape (OWUI, OpenAI SDK, Anthropic SDK; streaming and not; Ollama and oMLX) through the live pipeline, which is the check to repeat after changes to the router.
