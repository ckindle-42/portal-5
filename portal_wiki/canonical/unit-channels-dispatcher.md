---
id: unit-channels-dispatcher
kind: mixed
title: "Channels dispatcher \u2014 shared pipeline call + retry transport"
sources:
- type: code
  path: portal_channels/dispatcher.py
  commit: 5b73259d
last_generated_commit: 41df61e0a6102275a700700e9765972f1508c4c5
claims: []
confidence: high
tags:
- authored-v1
- channels
created_at: 1785795345.853102
updated_at: 1785795345.853102
---

The channel dispatcher is the shared transport that both channel adapters
(Slack and Telegram) use to reach the pipeline. It is the only place in the
channels package that knows how to talk to `portal-pipeline` at :9099: it
builds the chat-completions payload, authenticates with the pipeline API key,
calls with retry and exponential backoff on transient failures, and validates
workspace names against the canonical roster.

## Why

Both adapters need the same call behaviour — a 120-second timeout, three
retries with backoff on connection errors and 5xx responses, and a single
response string extracted from the OpenAI-compatible completion shape — and
duplicating that in each bot is exactly the drift this module prevents.
`VALID_WORKSPACES` is a frozen snapshot of the canonical workspace ids so the
Telegram `/workspace` command can reject unknown names client-side instead of
letting a typo reach the pipeline. The retry logic treats `5xx` and connection
errors as transient but lets 4xx propagate immediately — a bad workspace name
should fail fast, not be retried.

## Interfaces

`call_pipeline_sync` serves the Slack handlers (which run in a thread pool)
and `call_pipeline_async` the Telegram handlers; both build the payload with
`_build_payload`, sign it with `_auth_headers`, and retry per `PIPELINE_RETRIES`.
`is_valid_workspace` is the roster check. The payload embeds the workspace as
the model field so the pipeline's router picks the right workspace without the
adapter knowing routing internals.

## Gotchas

`call_pipeline_async` takes a `history` argument so Telegram can send its
bounded conversation window — the payload carries the whole message list, not
just the new text. Retry backoff is exponential (`2**attempt` seconds), so the
total worst-case wait is one plus two seconds before the final attempt.
