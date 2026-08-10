---
id: unit-known-limitations-post-v1-messages-anthropic-compat-endpoint-returns-http-200-with-a-null-body
kind: what
title: "KNOWN_LIMITATIONS \u2014 POST /v1/messages Null Success Body (Resolved)"
sources:
- type: code
  path: portal/platform/inference/router/handlers.py
- type: code
  path: portal/platform/inference/router/anthropic_compat.py
- type: code
  path: tests/unit/test_pipeline.py
last_generated_commit: de01e9b1e91aa629f9d80d26a890483a552e43e0
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.671825
updated_at: 1784946220.671825
---

- **ID**: P5-ANTHROPIC-COMPAT-001
- **Status**: RESOLVED 2026-07-29.
- **Former issue**: The non-streaming `/v1/messages` (Anthropic Messages API) success path completed after checking the loopback response status but did not return the translated response, so FastAPI serialized Python `None` as `null` — HTTP 200 with an empty body.
- **Resolution**: `anthropic_messages` in `portal/platform/inference/router/handlers.py` now returns `openai_response_to_anthropic(resp.json(), model_id)` on HTTP 200 (line ~1328). The translation lives in `portal/platform/inference/router/anthropic_compat.py`. Error propagation and the streaming translation path are unchanged.
- **Regression coverage**: `test_anthropic_non_streaming_success_returns_message` in `tests/unit/test_pipeline.py` exercises the ASGI loopback and asserts the complete Anthropic Messages response shape, content, stop reason, model, and token usage.
- **Discovered**: 2026-07-13, live-verifying the opencode CLI-contract migration.

## Why

An Anthropic-compatible endpoint returning HTTP 200 with a null body is the worst possible failure mode for a CLI client: the request looks successful so the client waits for a response that never arrives. The fix keeps the loopback pattern for routing but makes the return value explicit, and the test asserts the full wire shape rather than just the status code, so a regression reintroducing the silent null is caught at the contract level.
