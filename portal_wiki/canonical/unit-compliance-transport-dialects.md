---
id: unit-compliance-transport-dialects
kind: mixed
title: "Compliance transport dialects — the sweep's wire protocol seam"
sources:
- type: code
  path: portal/modules/compliance/core/transport_dialects.py
  commit: 26f2ed03
- type: code
  path: portal/modules/compliance/core/reading_transport.py
  commit: 26f2ed03
- type: code
  path: tests/unit/test_compliance_reading_transport.py
  commit: 26f2ed03
claims: []
confidence: high
tags:
- authored-v1
- module
- compliance
- transport

---

The compliance reading call speaks one wire protocol at a time, and the choice
lives in `transport_dialects`, not in the transport's call logic. A dialect
is the difference between two wire protocols and nothing else: it builds a
request body, unpacks a response body, reports its own latency metrics, names
where its context window comes from, and stamps its own name and endpoint onto
every result. `reading_transport.chat` keeps what is protocol-independent —
the answer/reasoning budget split, the empty-answer retry, the thinking
downgrade record — and delegates the protocol-specific parts to the resolved
dialect.

## Why

The transport defaults to the Portal pipeline, which owns routing, fallback,
sampling enforcement and tool-call recovery. The native Ollama passthrough is
the explicit rollback. Every result records the dialect and endpoint that
served it, and an unknown dialect name is an error rather than a silent
fallback.

## Interfaces

`resolve_dialect(dialect)` resolves an explicit name, then the
`COMPLIANCE_TRANSPORT` env var, and defaults to `pipeline`. The
`ollama-native` rollback speaks `/api/chat` with
`options.{temperature,num_predict,num_ctx}` and top-level
`keep_alive`/`think`. The production `PipelineCompat` speaks the pipeline's
OpenAI-compatible `/v1/chat/completions` endpoint, passes workspace IDs and
client tools, and records routing attribution from the pipeline trace.

`OllamaNative` defaults `OLLAMA_BASE` to the pipeline's `/ollama` passthrough,
and authenticates with `PIPELINE_API_KEY`. Its `/api/show` and `/api/ps` reads
use the same base and auth headers, so native rollback calls retain their
request-time `num_ctx` behavior while still going through host-memory admission.
