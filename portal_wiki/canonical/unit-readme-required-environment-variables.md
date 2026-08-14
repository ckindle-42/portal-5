---
id: unit-readme-required-environment-variables
kind: what
title: "README \u2014 Required Environment Variables"
sources:
- type: code
  path: .env.example
- type: code
  path: deploy/portal-5/docker-compose.yml
- type: code
  path: portal/platform/inference/router/auth.py
- type: code
  path: scripts/lib/util.sh
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.689932
updated_at: 1784946220.689932
---

| Variable | Required | Description |
|----------|----------|-------------|
| `PIPELINE_API_KEY` | **Yes** | API key for pipeline authentication. Generate with: `openssl rand -hex 32`. Pipeline will not start without this. |

`PIPELINE_API_KEY` is the one variable every authenticated path depends on:
`portal/platform/inference/router/auth.py` compares every request's `Authorization`
Bearer token against it (constant-time via `hmac.compare_digest`), and
`deploy/portal-5/docker-compose.yml` passes it to the pipeline, Open WebUI
(`OPENAI_API_KEY`) and the Telegram/Slack bots. The pipeline refuses requests that
do not carry a matching token.

`./launch.sh up` removes the setup burden: the `up` case in `launch.sh` calls
`bootstrap_secrets` and a repair loop over `PIPELINE_API_KEY`, `WEBUI_SECRET_KEY`,
`OPENWEBUI_ADMIN_PASSWORD`, `SEARXNG_SECRET_KEY` and `GRAFANA_PASSWORD`, so a key
left at `CHANGEME` or missing is replaced with a generated secret before the stack
starts.

## Why

A single shared API key keeps the pipeline, the chat UI and the channel bots
authenticated against one credential instead of several hand-managed secrets, and
generating it automatically in `up` means a first-time operator never has to
produce or paste a random value. The remaining secrets are likewise auto-generated
so `.env` is usable the moment it is created.
