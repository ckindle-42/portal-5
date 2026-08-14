---
id: unit-alerts-3-restart-the-pipeline
kind: what
title: "ALERTS \u2014 3. Restart the pipeline"
sources:
- type: code
  path: deploy/portal-5/docker-compose.yml
- type: code
  path: portal/platform/inference/router/lifespan.py
- type: code
  path: portal/platform/inference/notifications/dispatcher.py
- type: code
  path: .env.example
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.5452852
updated_at: 1784946220.5452852
---

The notification subsystem reads its entire configuration from environment variables during process startup, so editing `.env` has no effect until the pipeline container is recreated. The compose file at deploy/portal-5/docker-compose.yml defines the service as `portal-pipeline` and forwards every alert variable, so `docker compose restart portal-pipeline`, run from the compose directory, is the documented refresh path; `./launch.sh up` also recreates containers whose configuration changed.

## Why

Because the dispatcher, scheduler, and channels bind their values once at lifespan startup, there is no hot-reload path; a restart is the only way to apply a new webhook URL or token. Calling the exact command out prevents operators from editing environment files, seeing nothing change, and assuming the alert layer is broken when it simply has not been restarted.
