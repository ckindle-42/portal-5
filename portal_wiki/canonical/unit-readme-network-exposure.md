---
id: unit-readme-network-exposure
kind: what
title: "README \u2014 Network Exposure"
sources:
- type: code
  path: deploy/portal-5/docker-compose.yml
- type: code
  path: portal/platform/inference/router/auth.py
- type: code
  path: scripts/lib/util.sh
- type: code
  path: .env.example
last_generated_commit: a81c5e73569f981ecedb0d95b088563fcce651ed
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.690359
updated_at: 1784946220.690359
---

By default the Portal Pipeline binds to all interfaces. `deploy/portal-5/docker-compose.yml`
maps `0.0.0.0:9099:9099`, so other machines on the LAN can reach it — intentional
for multi-device setups. Requests are protected by `PIPELINE_API_KEY` authentication:
`portal/platform/inference/router/auth.py` compares the `Authorization` Bearer
token against the key with `hmac.compare_digest` and rejects mismatches, so an
exposed port does not mean an open API.

Open WebUI is the component that defaults to loopback: `launch.sh` derives
`WEBUI_LISTEN_ADDR` from `ENABLE_REMOTE_ACCESS` in `.env` and writes it into the
compose mapping (`${WEBUI_LISTEN_ADDR:-127.0.0.1}:8080:8080`). Set
`ENABLE_REMOTE_ACCESS=true` in `.env` to bind Open WebUI on all interfaces.

## Why

The asymmetry is deliberate: the pipeline must be reachable from LAN clients and
channel bots, so it exposes 0.0.0.0 and leans on the API key; the chat UI has no
key of its own and should not be silently world-visible, so it defaults to
loopback unless the operator opts into remote access. Firewall guidance applies to
a LAN, not the public internet.
