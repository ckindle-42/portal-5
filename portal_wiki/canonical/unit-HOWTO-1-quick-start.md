---
id: unit-HOWTO-1-quick-start
kind: why
title: "HOWTO \u2014 1. Quick Start"
sources:
- type: code
  path: launch.sh
- type: code
  path: .env.example
claims: []
confidence: high
tags:
- HOWTO
- docs
- verified-v1
created_at: 1783195000.838752
updated_at: 1783195000.838752
---

Complete working examples for every feature. Each section shows: what it does, how to activate it, a working example, and how to verify.

**What:** Launch the entire platform with one command.

```bash
git clone https://github.com/ckindle-42/portal-5.git
cd portal-5
./launch.sh up
```

The `up` case in `launch.sh` copies `.env.example` to `.env` when it is missing, regenerates any secret still set to `CHANGEME` via `bootstrap_secrets` and the secret-repair loop, creates the shared workspace tree under `~/AI_Output`, pulls the Docker images, auto-starts the native services, checks hardware, and brings the compose stack up. A first run downloads images and model weights, so it takes tens of minutes rather than seconds; subsequent runs are near-instant.

When the stack is ready `launch.sh` prints the service URLs:

- Open WebUI: `http://localhost:8080`
- SearXNG: `http://localhost:8088`
- ComfyUI: `http://localhost:8188`
- Grafana: `http://localhost:3000`
- Prometheus: `http://localhost:9090`

`ENABLE_REMOTE_ACCESS=true` in `.env` makes Open WebUI bind to `0.0.0.0` instead of loopback, and `WEBUI_LISTEN_ADDR` is written back into `.env` so external restarts keep the same binding.

**Verify:**
```bash
./launch.sh status
```

## Why

First-run bootstrapping lives inside the `up` case rather than in a manual checklist so every post-clone dependency — env file, secrets, workspace tree, Docker images, model weights — is generated or fetched by one command and a fresh checkout converges to the same running stack as an old install. The secret-repair loop also makes an interrupted first run self-healing: re-running `up` regenerates whatever placeholder value is left over.
