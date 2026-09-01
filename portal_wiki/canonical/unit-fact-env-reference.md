---
id: unit-fact-env-reference
kind: mixed
title: "Environment variables \u2014 the .env.example families"
sources:
- type: code
  path: .env.example
- type: code
  path: deploy/portal-5/docker-compose.yml
- type: code
  path: launch.sh
claims:
- probe: env.vars
  pattern: '{value} env vars'
confidence: high
tags:
- fact
- operator
created_at: 1788030600.446044
updated_at: 1788030600.446044
---

# Environment variables — the .env.example families

The operator's runtime configuration lives in `.env`, copied from
`.env.example` on first `up`; the example file declares 233 env vars, grouped
by what they tune. Every var carries an inline or section comment so a knob is
never a bare secret.

## Core secrets and admin

- `PIPELINE_API_KEY`, `WEBUI_SECRET_KEY`, `SEARXNG_SECRET_KEY`,
  `GRAFANA_PASSWORD` — auto-generated on first run; the secrets the stack signs
  and authenticates with.
- `OPENWEBUI_ADMIN_*` — the first-run admin account.

## Media and speech

- `TTS_DEFAULT_VOICE`, `MUSIC_MODEL_SIZE`, `MAX_MUSIC_FILES` — default voice,
  music model size, and file retention.
- `AUDIO_STT_ENGINE` — Open WebUI's auto-transcription of audio uploads and
  microphone input.

## Sandbox and execution

- `SANDBOX_TIMEOUT`, `SANDBOX_ALLOW_NETWORK`, `SANDBOX_LAB_EXEC` — the
  isolated code-execution posture; the last swaps in the attack-image lab
  envelope with `LAB_TARGET_*` connectivity.
- `AIOHTTP_CLIENT_TIMEOUT`, `AIOHTTP_CLIENT_TIMEOUT_TOOL_SERVER_DATA` — tool
  server request and data-read ceilings.

## RAG and retrieval

- `RAG_RERANK_ENABLED`, `RAG_CANDIDATE_POOL_SIZE`, `RERANKER_URL`,
  `RERANKER_MODEL` — the two-stage rerank pipeline.

## Lab, Proxmox, and MBPTL

- `LAB_SPLUNK_*`, `SPLUNKBASE_*` — the Splunk injection lane and install-time
  Splunkbase account.
- `LAB_MBPTL_*`, `PROXMOX_URL`, `PROXMOX_TOKEN_ID`, `PROXMOX_TOKEN_SECRET`,
  `PROXMOX_VERIFY_SSL` — the MBPTL CTF lab and Proxmox control plane.

## Ports, channels, and loops

- `*_HOST_PORT` overrides — re-map MCP container ports if the defaults are
  taken.
- `TELEGRAM_BOT_TOKEN`, `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN` — messaging
  channels.
- `TOOL_REGISTRY_REFRESH_S`, `LOOP_NOTIFY_ENABLED`, `LOOP_NOTIFY_ON_SUCCESS` —
  tool rediscovery cadence and security-loop notifications.

## Why

Two rules keep the env surface honest: the example file is the single source
for every var the stack reads (nothing is invented in `docker-compose.yml`),
and every var carries a comment so an operator knows what toggling it costs.
The families above mirror the section headers in the file, so a var is found
either by name or by the surface it tunes.
