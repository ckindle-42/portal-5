---
id: unit-known-limitations-no-built-in-multi-user-rate-limiting
kind: what
title: "KNOWN_LIMITATIONS \u2014 No Built-in Multi-User Rate Limiting"
sources:
- type: code
  path: portal/platform/inference/router/concurrency.py
- type: code
  path: portal/platform/inference/router/streaming.py
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.6616168
updated_at: 1784946220.6616168
---

- **ID**: P5-ROAD-031
- **Description**: There is no per-user rate limiting in the stack. The pipeline's only throttle is request-concurrency limiting in `portal/platform/inference/router/concurrency.py` (`RequestSlot`, `_request_semaphore`, `_workspace_semaphores`), which bounds in-flight conversations per workspace but does not distinguish users; `streaming.py` documents that a slot is held for the entire multi-hop conversation, not per HTTP request. Open WebUI, the multi-user front end, adds no per-user quota of its own. A single user in a multi-user deployment can therefore exhaust server resources.
- **Mitigation**: Deploy behind a reverse proxy (nginx, Traefik) with rate limiting, or use Open WebUI's admin controls for per-user quotas.

## Why

Concurrency slots protect the backend from oversubscription but were never designed to arbitrate between users — they treat every request as equally entitled to a slot. Per-user fairness is a product-level policy that the pipeline deliberately does not guess at, so the boundary is documented: the operator who needs multi-tenant isolation must enforce it at the proxy layer where user identity is actually visible.
