---
id: unit-known-limitations-no-built-in-multi-user-rate-limiting
kind: what
title: "KNOWN_LIMITATIONS \u2014 No Built-in Multi-User Rate Limiting"
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  commit: 05e42ec2
  section: No Built-in Multi-User Rate Limiting
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.6616168
updated_at: 1784946220.6616168
---

- **ID**: P5-ROAD-031
- **Description**: Open WebUI has no per-user rate limiting. A single user in a multi-user deployment can exhaust server resources.
- **Mitigation**: Deploy behind a reverse proxy (nginx, Traefik) with rate limiting, or use Open WebUI's admin controls for per-user quotas.

---
