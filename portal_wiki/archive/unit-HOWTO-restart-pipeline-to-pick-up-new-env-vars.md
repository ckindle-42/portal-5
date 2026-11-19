---
id: unit-HOWTO-restart-pipeline-to-pick-up-new-env-vars
historical: true
kind: why
title: "HOWTO \u2014 Restart pipeline to pick up new env vars"
sources:
- type: design
  path: docs/HOWTO.md
  section: Restart pipeline to pick up new env vars
confidence: high
tags:
- docs
- HOWTO

---

docker compose -f deploy/portal-5/docker-compose.yml restart portal-pipeline
