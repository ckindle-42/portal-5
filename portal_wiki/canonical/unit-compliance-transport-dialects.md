---
id: unit-compliance-transport-dialects
kind: mixed
title: "Compliance transport dialects — the sweep's wire protocol seam"
sources:
- type: code
  path: portal/modules/compliance/core/transport_dialects.py
  commit: 8720b60a
- type: code
  path: portal/modules/compliance/core/reading_transport.py
  commit: 8720b60a
- type: code
  path: tests/unit/test_compliance_reading_transport.py
  commit: 8720b60a
claims: []
confidence: high
tags:
- authored-v1
- module
- compliance
- transport
created_at: 1789944401.011186
updated_at: 1789944401.011186
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

The sweep's endpoint was a hardcoded Ollama constant
(`reading_transport._ENDPOINT`), which is why registering splash with the
PIPELINE never moved the sweep: `sweep.map_read` never consults
`backends.yaml` or the router. Wiring a new engine into the wrong lane would
change the conversation surface and leave the measured lane untouched — the
wrong-lane failure SPLASH_SWEEP_ACCELERATION_V1 exists to prevent. The seam
also carries the attribution rule the promotion decision depends on: every
result records the dialect and endpoint that served it, an unknown dialect name
is an error rather than a silent fallback, and splash's context window is a
serve-line pin (`--max-context 32768`) that a request cannot raise, so a
receipt can never claim a window its engine did not set.

## Interfaces

`resolve_dialect(dialect)` resolves an explicit name, then the
`COMPLIANCE_TRANSPORT` env var, then `ollama-native`; the default is
byte-identical to the pre-seam transport. `OllamaNative` speaks
`/api/chat` with `options.{temperature,num_predict,num_ctx}` and top-level
`keep_alive`/`think`. `OpenAICompat` speaks splash 1.0.1's
`/v1/chat/completions`: `max_tokens`/`temperature` top-level, no
`keep_alive`, `num_ctx` and `keep_alive` deliberately dropped,
`reasoning_effort` in place of `think`, and Bearer auth from
`SPLASH_API_KEY`.
