---
id: unit-router-streaming
kind: mixed
title: "Router streaming \u2014 policy-free SSE transport + tool loop"
sources:
- type: code
  path: portal/platform/inference/router/streaming.py
  commit: b1392f8efd4cbdaf0f760a1a023f67c494b14b7e
claims: []
confidence: high
tags:
- authored-v1
- platform
- inference
- router
created_at: 1785798117.610343
updated_at: 1785798117.610343
---

`streaming.py` is the streaming transport — pure bytes-in / SSE-bytes-out
with no routing policy. It owns the tool-loop streaming, the chain handoff,
the preamble injection, and the JSON-to-SSE conversion for the fallback
path.

## Why

Streaming is where the pipeline's hard-won lessons live, and the module's
docstring is explicit that it is transport-only: no routing policy, because
mixing policy into the stream made the module untestable and let a routing
change break the SSE shape. The tool loop (`_stream_with_tool_loop`) is the
semaphore-owning multi-hop dispatch that lets a model call tools mid-stream;
the chain handoff (`_stream_with_chain`) serialises a multi-model chain;
and `_stream_with_secondary_chain` is the legacy shim that delegates to the
chain — a unit describing it as a separate two-model pipeline would be
confidently wrong. The FX1 lesson (a dependency-contract mismatch that unit
mocks could not catch) is why the live streaming smoke test exists.

Within one turn a `ToolRepeatGuard` (`router/tool_repeat.py`) answers a call the model re-issues with identical arguments from its earlier result plus a short note, instead of running the tool again (read-only tools only: any other call, such as `execute_bash` or a write, always runs and clears what was cached, so an edit followed by the same test command is not a repeat), and on a third identical request the next hop withholds the tools so the turn ends with an answer rather than the hop limit. The non-streaming failover loop applies the same guard; each suppression increments `portal5_tool_repeat_suppressed_total{workspace}`. A workspace flagged `require_tool_before_answer` in portal.yaml (auto-data) does not deliver an answer given with no tool call in the whole turn: the hop's output is held, the model is asked once to answer from a query (tools still offered, `portal5_answer_without_tool_retried_total{workspace}`), and an answer that is still ungrounded is delivered with a one-line notice.

## Interfaces

`_json_completion_to_sse`, `_stream_from_backend_guarded`,
`_stream_with_chain`, `_stream_with_preamble`,
`_stream_with_secondary_chain`, `_stream_with_tool_loop`, and
`_stream_with_tool_loop_impl`.

## Gotchas

Any change to this module or the streaming paths of `router_pipe` must run
the live streaming smoke test — unit mocks cannot detect the
dependency-contract mismatches this module historically produced.
