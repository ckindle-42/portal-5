---
id: unit-ADMIN_GUIDE-network-exposure
kind: why
title: "ADMIN_GUIDE \u2014 Network Exposure"
sources:
- type: code
  path: deploy/portal-5/docker-compose.yml
- type: code
  path: .env.example
- type: code
  path: scripts/mlx-speech.py
- type: code
  path: portal/platform/mcp_host/pipeline_mcp.py
claims: []
confidence: high
tags:
- ADMIN_GUIDE
- docs
- verified-v1
created_at: 1783195000.8136199
updated_at: 1783195000.8136199
---

Bindings are per-service in `deploy/portal-5/docker-compose.yml`. Open WebUI publishes `${WEBUI_LISTEN_ADDR:-127.0.0.1}:8080` — localhost unless `ENABLE_REMOTE_ACCESS=true`, and the shipped `.env.example` sets that flag true, so a fresh install listens on `0.0.0.0`. The Docker MCP servers (8910-8926), SearXNG (8088), and Prometheus (9090) bind `127.0.0.1`. The pipeline API binds `0.0.0.0:9099` and Grafana binds `0.0.0.0:3000`. Host-native MCP servers default to `0.0.0.0` — `scripts/mlx-speech.py`, `scripts/mlx-transcribe.py`, `portal/platform/mcp_host/pipeline_mcp.py`, and the security/wiki MCPs. The external boundary is therefore the firewall plus the tunnel/proxy path, not a universal loopback guarantee.

## Why

"Everything is localhost" is a false comfort on this stack: compose services and host-native services bind differently, and the pipeline deliberately listens on all interfaces so the host MCPs and remote backends can reach it. Knowing exactly which surfaces are network-visible is what makes the recommended tunnel approach safe — it publishes only the media paths, not the full API plane.
