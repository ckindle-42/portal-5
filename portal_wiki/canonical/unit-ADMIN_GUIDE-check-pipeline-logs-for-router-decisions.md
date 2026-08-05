---
id: unit-ADMIN_GUIDE-check-pipeline-logs-for-router-decisions
kind: why
title: "ADMIN_GUIDE \u2014 Check pipeline logs for router decisions"
sources:
- type: code
  path: launch.sh
- type: code
  path: portal/platform/inference/router/routing.py
- type: code
  path: portal/platform/inference/router/handlers.py
last_generated_commit: ca0f99d64c0644df1d5fc30674b6c476fceb1a42
claims: []
confidence: high
tags:
- ADMIN_GUIDE
- docs
- verified-v1
created_at: 1783195000.8175411
updated_at: 1783195000.8175411
---

Router decisions are logged by the pipeline. The LLM layer logs each confident classification from `_route_with_llm` in routing.py as `LLM router: '<text>' → workspace='<id>' confidence=<n>`, and every timeout, low-confidence result, or error logs "falling back to keywords". The dispatch layer logs `Routing workspace=<id>` in handlers.py when a request is sent to a backend. `./launch.sh logs` tails the portal-pipeline container by default (the `logs` case runs `docker compose logs -f portal-pipeline`). A practical filter is:

```bash
./launch.sh logs | grep -E "LLM router|Routing workspace|falling back to keywords"
```

## Why

Misrouted requests are decided at a single point, so the router logs are the first place to look when a user reports the wrong workspace. The `confidence` field distinguishes a genuinely low-confidence classification from a timeout, which separates a model-quality problem from a latency problem before any deeper debugging starts.
