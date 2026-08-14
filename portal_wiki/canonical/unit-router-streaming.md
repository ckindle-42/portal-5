---
id: unit-router-streaming
kind: mixed
title: "Router streaming \u2014 policy-free SSE transport + tool loop"
sources:
- type: code
  path: portal/platform/inference/router/streaming.py
  commit: 86e6f142c0069ca2d4824b4721a545e64bd585b3
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

## Interfaces

`_json_completion_to_sse`, `_stream_from_backend_guarded`,
`_stream_with_chain`, `_stream_with_preamble`,
`_stream_with_secondary_chain`, `_stream_with_tool_loop`, and
`_stream_with_tool_loop_impl`.

## Gotchas

Any change to this module or the streaming paths of `router_pipe` must run
the live streaming smoke test — unit mocks cannot detect the
dependency-contract mismatches this module historically produced.
