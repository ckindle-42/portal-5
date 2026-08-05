---
id: unit-readme-quick-start
kind: what
title: "README \u2014 Quick Start"
sources:
- type: code
  path: launch.sh
- type: code
  path: scripts/lib/util.sh
- type: code
  path: .env.example
- type: code
  path: deploy/portal-5/docker-compose.yml
last_generated_commit: f28832a459fb834ed6696f953f9955694b962483
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.678459
updated_at: 1784946220.678459
---

```bash
git clone https://github.com/ckindle-42/portal-5.git
cd portal-5
./launch.sh up
```

The `up` case in `launch.sh` does the whole first boot: it copies `.env.example`
to `.env` if missing, generates any secrets still set to CHANGEME, initializes the
shared workspace directories, stops any previously running stack, pulls Docker
images, runs the hardware and port pre-flight checks, starts the compose stack
(profiles auto-selected from Telegram/Slack tokens), and launches the ARM64
embedding server on Apple Silicon. The `ollama-init` compose service pulls the
three core models (see the core-models unit).

When it finishes, the terminal prints the real endpoint list:

```
[portal-5] Stack started.
  Open WebUI:  http://localhost:8080
  SearXNG:     http://localhost:8088
  ComfyUI:     http://localhost:8188
  Grafana:     http://localhost:3000  (admin / check .env)
  Prometheus:  http://localhost:9090
```

Sign in at http://localhost:8080 with the admin credentials in `.env`
(`OPENWEBUI_ADMIN_EMAIL` defaults to `admin@portal.local`, password is the
auto-generated `OPENWEBUI_ADMIN_PASSWORD`). Do not commit `.env`.

## Why

The zero-setup contract is that a fresh machine reaches a usable stack from one
command: secret generation, workspace init, hardware checks and model bootstrap
all happen inside `up` so the operator never hand-edits a config to get started.
The printed endpoints are the actual compose service URLs, so the first login uses
credentials that already exist in `.env`.
