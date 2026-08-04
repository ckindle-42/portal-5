---
id: unit-known-limitations-request-size-cap-relies-on-content-length-only
kind: what
title: "KNOWN_LIMITATIONS \u2014 Request-Size Cap Relied on Content-Length Only (Resolved)"
sources:
- type: code
  path: portal/platform/inference/router/request_limits.py
- type: code
  path: tests/unit/test_request_limits.py
last_generated_commit: 0a5fcb6eea38bf284a96ceea702849491ba4d1c7
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.6726248
updated_at: 1784946220.6726248
---

- **ID**: P5-REQ-SIZE-001
- **Status**: RESOLVED 2026-07-29.
- **Former issue**: The pipeline enforced its request-size cap only through `Content-Length`, so HTTP chunked transfer encoding bypassed the limit — a client could stream an oversized inference body past the check.
- **Resolution**: `RequestBodyLimitMiddleware` in `portal/platform/inference/router/request_limits.py` buffers and bounds the two JSON inference endpoints before route handling, enforcing the same limit against declared and streamed/chunked bodies. Its module docstring documents that a `Content-Length`-only check is bypassed by chunked transfer. Oversize requests return 413 before the handler runs.
- **Regression coverage**: `test_chunked_body_over_limit_is_rejected_before_handler` in `tests/unit/test_request_limits.py` sends a chunked async body with no usable `Content-Length` and verifies rejection with status 413.

## Why

`Content-Length` is a header the client controls, and chunked transfer omits it entirely, so trusting it for a size cap leaves the endpoint unbounded for any client that speaks HTTP/1.1 chunking. Middleware that reads the actual ASGI body stream and enforces the same ceiling on what it consumes closes the gap at the transport layer, and the chunked regression test proves the exact bypass that motivated it.
