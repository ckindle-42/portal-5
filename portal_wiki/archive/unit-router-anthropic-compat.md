---
id: unit-router-anthropic-compat
kind: mixed
title: "Router anthropic compat \u2014 Messages-API translation layer"
sources:
- type: code
  path: portal/platform/inference/router/anthropic_compat.py
  commit: a234187e
last_generated_commit: a234187e
claims: []
confidence: high
tags:
- authored-v1
- platform
- inference
- router
created_at: 1785798040.539374
updated_at: 1785798040.539374
---

The Anthropic compatibility layer converts between the Anthropic
`/v1/messages` wire format and the pipeline's internal OpenAI-compatible
format, enabling Claude Code and any `anthropic` SDK client to use the local
model fleet.

## Why

Claude Code speaks the Anthropic Messages API, and the pipeline speaks
OpenAI's chat-completions shape. Without a translation layer, a local
deployment could not serve Claude Code at all — it would need a cloud
Anthropic endpoint, which the zero-cloud promise forbids. The adapter is the
boundary that makes "Claude Code against local models" work: requests
translate in, responses translate back, including the streaming SSE form.
The two-way conversion is the whole surface — a one-way adapter would serve
requests and then fail to return responses the client could read.

## Interfaces

`anthropic_to_openai_body` converts an incoming request;
`openai_response_to_anthropic` and `openai_stream_to_anthropic_sse` convert
responses (non-streaming and streaming).

## Gotchas

The streaming conversion is the subtle half — Anthropic and OpenAI SSE
frames differ in both shape and event names, and a mismatch there silently
breaks the tool loop, which is why the streaming path is tested separately.
