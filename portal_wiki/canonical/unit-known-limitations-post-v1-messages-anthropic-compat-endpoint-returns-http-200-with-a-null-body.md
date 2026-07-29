---
id: unit-known-limitations-post-v1-messages-anthropic-compat-endpoint-returns-http-200-with-a-null-body
kind: what
title: "KNOWN_LIMITATIONS \u2014 POST /v1/messages Null Success Body (Resolved)"
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  commit: 05e42ec2
  section: POST /v1/messages (Anthropic-compat endpoint) returns HTTP 200 with a `null`
    body
- type: code
  path: portal/platform/inference/router/handlers.py
- type: code
  path: tests/unit/test_pipeline.py
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.671825
updated_at: 1784946220.671825
---

- **ID**: P5-ANTHROPIC-COMPAT-001
- **Status**: RESOLVED 2026-07-29.
- **Former issue**: The non-streaming success path completed after checking the
  loopback response status but never returned the translated response, so
  FastAPI serialized Python `None` as `null`.
- **Resolution**: The handler now returns
  `openai_response_to_anthropic(resp.json(), model_id)` on HTTP 200. Error
  propagation and the streaming translation path are unchanged.
- **Regression coverage**: The endpoint test exercises the ASGI loopback and
  asserts the complete Anthropic Messages response shape, content, stop reason,
  model, and token usage.
- **Discovered**: 2026-07-13, live-verifying `DESIGN_OPENCODE_ADDRESSING_V1.md`'s
  Step 3e CLI-contract migration (`cc-local.sh`'s default model rename).
