---
id: unit-capability-turn-trace
kind: mixed
title: "Turn trace — per-turn operational record"
sources:
- type: code
  path: portal/platform/inference/router/trace.py
- type: code
  path: portal/platform/inference/router/handlers.py
- type: code
  path: portal/platform/inference/router/streaming.py
- type: code
  path: portal/platform/inference/router/non_streaming.py
- type: code
  path: portal/platform/inference/router/tools.py
- type: code
  path: portal/platform/inference/ollama_native.py
- type: code
  path: portal/platform/inference/router/correlation.py
- type: code
  path: deploy/portal-5/docker-compose.yml
claims: []
confidence: high
tags:
- capability
- observability
- platform
---

# Turn trace — per-turn operational record

## What

`trace.py` keeps one JSON record per chat turn: the workspace the router
resolved, the persona, the backend and model that answered, and a span for
every tool the model asked for — including one the persona whitelist refused,
which `_dispatch_tool_call` records as `allowed=false` before the gate runs.
`start_trace` binds a `TurnTrace` to the request inside `chat_completions`
rather than in `CorrelationIdMiddleware`, because the middleware resets its
contextvar as soon as `call_next` returns and a streaming body is produced
after that point, in a child task holding a copy of the context.

Records land in a tmpfs directory named by `PORTAL_TRACE_DIR`, keyed on the
correlation id echoed to the client as `X-Correlation-ID`. `PORTAL_TRACE`
disables capture outright, `PORTAL_TRACE_BODIES` opts into message and
argument text (each tool-loop hop's request is a digest: the messages new since the
previous hop with role, size, sha256 and a short head, so a 20-hop turn fits the
record cap), and `PORTAL_TRACE_MAX` caps how many records survive before the
oldest are pruned. `finalize_trace` overwrites rather than skipping a repeat
call: the handler writes the routing decision when its response headers are
ready, and the streaming generator replaces that record with the complete one
once the last tool hop is done. An operator reads them back through
`list_traces` and `get_trace`.

## Timing metadata

The record's top-level `portal_timings` object carries request-level
`prefill_s`, `ttft_s`, reasoning and answer counts and durations, `answer_tps`,
`tool_s`, `total_s` and `timing_source`. Model-call timing is accumulated across
tool-loop hops, while tool dispatch stays in `tool_s`. Streaming clients receive
the same object in a metadata-only chunk immediately before `[DONE]`; a
non-streaming response carries it in the body. Engine timing fields are marked
`engine`, and stream-derived timing fields are marked `measured`.
Per-model-call usage metrics receive the same timing rollup: generation duration and TTFT retain
engine provenance when supplied, stream-derived decode and TTFT are marked measured, and tool
dispatch time is excluded from decode and answer durations.

## Why

A directory rather than an in-process ring because `PIPELINE_WORKERS` defaults
to two and a ring would scatter turns across worker processes, so a lookup
would miss whenever it landed on the wrong one — the cross-process problem
`PROMETHEUS_MULTIPROC_DIR` already solves for metrics. The store stays
telemetry and never feeds a decision, which is what keeps Ground Rule 4 intact
while still answering the question metrics cannot: not how often a turn
failed, but what this particular turn did before it did.
