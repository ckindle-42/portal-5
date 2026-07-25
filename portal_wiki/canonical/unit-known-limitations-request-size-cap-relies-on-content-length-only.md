---
id: unit-known-limitations-request-size-cap-relies-on-content-length-only
kind: what
title: "KNOWN_LIMITATIONS \u2014 Request-Size Cap Relies on Content-Length Only"
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  commit: 05e42ec2
  section: Request-Size Cap Relies on Content-Length Only
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.6726248
updated_at: 1784946220.6726248
---

- **ID**: P5-REQ-SIZE-001
- **Description**: The pipeline caps requests at 4 MB via `Content-Length` header check. Chunked transfer-encoded requests bypass this cap entirely — Starlette middleware is the proper fix.
- **Mitigation**: Until Starlette body-size middleware is added, operators should configure upstream proxies (nginx, OWUI) to enforce request-size limits.
