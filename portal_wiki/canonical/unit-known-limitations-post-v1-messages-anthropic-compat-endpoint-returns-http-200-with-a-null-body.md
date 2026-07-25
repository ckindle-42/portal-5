---
id: unit-known-limitations-post-v1-messages-anthropic-compat-endpoint-returns-http-200-with-a-null-body
kind: what
title: "KNOWN_LIMITATIONS \u2014 POST /v1/messages (Anthropic-compat endpoint) returns\
  \ HTTP 200 with a `null` body"
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  commit: 05e42ec2
  section: POST /v1/messages (Anthropic-compat endpoint) returns HTTP 200 with a `null`
    body
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.671825
updated_at: 1784946220.671825
---

- **ID**: P5-ANTHROPIC-COMPAT-001
- **Description**: `handlers.anthropic_messages` (`portal/platform/inference/router/handlers.py:1159`,
  the endpoint `scripts/cc-local.sh` / Claude Code's `ANTHROPIC_BASE_URL` integration
  depends on) returns `200 OK` with a literal `null` JSON body for a plain
  non-streaming request, reproduced with both a base workspace id
  (`auto-coding`) and a persona slug (`agenticheavy`) — so it's unrelated to
  the alias-closeout/persona work in this pass, and pre-existing (zero unit
  test coverage exists for this endpoint; `/v1/chat/completions` itself
  works correctly for the same model ids, confirmed live). No server-side
  error is logged.
- **Impact**: Claude Code via `scripts/cc-local.sh` likely cannot get a real
  response today — the SDK would receive `null` where it expects an
  Anthropic Messages response object.
- **Discovered**: 2026-07-13, live-verifying `DESIGN_OPENCODE_ADDRESSING_V1.md`'s
  Step 3e CLI-contract migration (`cc-local.sh`'s default model rename).
- **Not fixed here**: root-causing `anthropic_to_openai_body`/the ASGI-loopback
  dispatch/`openai_response_to_anthropic` translation chain is a distinct
  bug outside Stage A's scope (alias/persona addressing, not the Anthropic
  wire-format translation layer). Needs its own investigation + unit tests.
