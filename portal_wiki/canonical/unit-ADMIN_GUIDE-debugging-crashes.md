---
id: unit-ADMIN_GUIDE-debugging-crashes
kind: what
title: "ADMIN_GUIDE \u2014 Debugging crashes"
sources:
- type: code
  path: launch.sh
- type: code
  path: portal/platform/inference/router/app.py
- type: code
  path: portal/platform/inference/router/handlers.py
last_generated_commit: ca0f99d64c0644df1d5fc30674b6c476fceb1a42
claims: []
confidence: high
tags:
- ADMIN_GUIDE
- docs
- verified-v1
created_at: 1784950000.0
updated_at: 1784950000.0
---

# Debugging crashes

When a service is down or a persona request fails, the first step is to
separate an inference-tier problem from a pipeline problem before touching
any containers.

## Ollama health and model list

Check that Ollama is up and list what is installed:

```bash
curl -s http://localhost:11434/api/tags | jq .
```

`/api/tags` is Ollama's model registry; a non-empty response proves the
inference tier is reachable and shows which GGUF models are present.

## Pipeline health

Check the Portal pipeline (the OpenAI-compatible router on :9099) and
every registered backend in one call:

```bash
curl -s http://localhost:9099/health/all | jq .
```

`/health/all` is mounted in `portal/platform/inference/router/app.py` and
returns per-backend status, so a healthy response means routing itself is
fine even when a specific model is not loaded.

## All services

```bash
./launch.sh status
```

`launch.sh status` reports the whole stack, so it is the broadest first
probe when the failure's origin is unknown.

## Why

Crash debugging needs a tier order: Ollama, then the pipeline, then the
full stack. Each command above is one cheap probe that names its tier, so
an operator can bisect a failure before restarting anything — the
pipeline cannot route to a backend that is down, and `launch.sh status`
is the catch-all when the symptom does not map to a single port. The
endpoints are grounded in the router app that mounts them and the
`launch.sh` dispatch that runs `status`.
