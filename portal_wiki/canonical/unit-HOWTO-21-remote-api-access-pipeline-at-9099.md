---
id: unit-HOWTO-21-remote-api-access-pipeline-at-9099
kind: why
title: "HOWTO \u2014 21. Remote API Access (Pipeline at :9099)"
sources:
- type: code
  path: portal/platform/inference/router/app.py
- type: code
  path: portal/platform/inference/router/handlers.py
last_generated_commit: bb686b68ebf5e92e85a9d94a58501f0566522beb
claims: []
confidence: high
tags:
- HOWTO
- docs
- verified-v1
created_at: 1783195000.860634
updated_at: 1783195000.860634
---

**What:** The Portal Pipeline exposes an OpenAI-compatible HTTP API on port 9099. Any tool that accepts a custom OpenAI base URL can connect directly — no Open WebUI required.

**Endpoints** (`portal/platform/inference/router/app.py`):

- `GET /v1/models` — `list_models`, workspaces + IDE-curated persona entries
- `POST /v1/chat/completions` — `chat_completions`, streaming included
- `POST /v1/messages` — Anthropic-compatible message passthrough
- `GET /v1/backends` — registry health
- `GET /health` — liveness

**Auth:** requests need `Authorization: Bearer ${PIPELINE_API_KEY}`; `PIPELINE_API_KEY` is in `.env` (auto-generated on first `./launch.sh up`). Open WebUI itself connects this way: `OPENAI_API_BASE_URL=http://portal-pipeline:9099/v1` in `deploy/portal-5/docker-compose.yml`. The port maps to `0.0.0.0:9099:9099`, so remote clients can reach it if the host is reachable.

**Verify:**
```bash
curl http://localhost:9099/health
curl http://localhost:9099/v1/models -H "Authorization: Bearer ${PIPELINE_API_KEY}"
```

## Why

Exposing the same router as a plain HTTP API is what lets Open WebUI, the Telegram and Slack bots, IDE pickers, and arbitrary scripts all share one routing brain. Because auth is a single shared bearer key rather than per-client state, any consumer can point its OpenAI client at the pipeline and inherit workspace routing, persona handling, and tool dispatch without knowing any of it.
