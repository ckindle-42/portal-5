---
id: unit-known-limitations-request-size-cap-relies-on-content-length-only
kind: what
title: "KNOWN_LIMITATIONS \u2014 Request-Size Cap Relied on Content-Length Only (Resolved)"
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  commit: 05e42ec2
  section: Request-Size Cap Relies on Content-Length Only
- type: code
  path: portal/platform/inference/router/request_limits.py
- type: code
  path: tests/unit/test_request_limits.py
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.6726248
updated_at: 1784946220.6726248
---

- **ID**: P5-REQ-SIZE-001
- **Status**: RESOLVED 2026-07-29.
- **Former issue**: The pipeline enforced its 4 MB cap only through
  `Content-Length`, so chunked transfer encoding bypassed the limit.
- **Resolution**: `RequestBodyLimitMiddleware` buffers and bounds the two JSON
  inference endpoints before route handling, enforcing the same limit against
  declared and streamed/chunked bodies. Oversize requests return 413 before
  the handler runs.
- **Regression coverage**: `tests/unit/test_request_limits.py` sends a chunked
  async body with no usable `Content-Length` and verifies rejection.
