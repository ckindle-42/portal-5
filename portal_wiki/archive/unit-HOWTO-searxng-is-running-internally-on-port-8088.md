---
id: unit-HOWTO-searxng-is-running-internally-on-port-8088
historical: true
kind: why
title: "HOWTO \u2014 SearXNG is running internally on port 8088"
sources:
- type: design
  path: docs/HOWTO.md
  section: SearXNG is running internally on port 8088
confidence: high
tags:
- docs
- HOWTO

---

docker compose -f deploy/portal-5/docker-compose.yml ps searxng
