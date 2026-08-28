---
id: unit-ADMIN_GUIDE-alternative-lan-reverse-proxy-caddy-nginx
kind: why
title: "ADMIN_GUIDE \u2014 Alternative: LAN reverse proxy (Caddy / nginx)"
sources:
- type: code
  path: deploy/portal-5/docker-compose.yml
- type: code
  path: launch.sh
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
created_at: 1783195000.814135
updated_at: 1783195000.814135
---

For deployments that skip Cloudflare Tunnel, a Caddy or nginx proxy on the same host plays the same role: proxy Open WebUI on `:8080`, set `PORTAL_PUBLIC_URL` to the proxy's public address and `OWUI_API_KEY` to an Open WebUI `sk-` key. Generated files then come back as `${PORTAL_PUBLIC_URL}/api/v1/files/{id}/content/{name}` on `:8080` — the same one-port story as the tunnel. Bindings are per-service in `docker-compose.yml`: the Docker MCP servers bind `127.0.0.1`, but the pipeline API binds `0.0.0.0:9099`, Grafana binds `0.0.0.0:3000`, and the host-native MCP servers (`scripts/mlx-speech.py`, `portal/platform/mcp_host/pipeline_mcp.py`) default to `0.0.0.0`. The proxy must be the only thing that exposes those surfaces; never proxy the bare MCP tool APIs or the `:8080`-adjacent ports.

## Why

The loopback-only posture is enforced per service, not globally, so an operator who assumes "everything is localhost" will misread the network map. The proxy's job is to publish exactly the media-file paths users click in chat and nothing else, which is why the ingress example is path-scoped rather than a blanket pass-through of the whole API plane.
