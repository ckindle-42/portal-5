---
id: unit-ADMIN_GUIDE-alternative-lan-reverse-proxy-caddy-nginx
kind: why
title: "ADMIN_GUIDE \u2014 Alternative: LAN reverse proxy (Caddy / nginx)"
sources:
- type: design
  path: docs/ADMIN_GUIDE.md
  section: 'Alternative: LAN reverse proxy (Caddy / nginx)'
last_generated_commit: ''
confidence: high
tags:
- docs
- ADMIN_GUIDE
created_at: 1783195000.814135
updated_at: 1783195000.814135
---


For deployments that don't use Cloudflare Tunnel, a Caddy or nginx reverse proxy on the same machine can serve the same role. Reverse-proxy `/files/{music,tts,video}/*` and `/comfyui/*` to the corresponding loopback ports, set `PORTAL_PUBLIC_URL` to the proxy's public address, and the same env-var derivation works. A first-class Caddy profile in `docker-compose.yml` is on the roadmap but not yet implemented.

**Never expose the MCP ports directly to the internet.** Routing only `/files/{kind}/*` keeps the rest of the MCP API surface private.

The pipeline API (port 9099) and all MCP servers (8910–8923) are always bound to 127.0.0.1 and are not reachable externally under any configuration. Cloudflare Tunnel reaches them via the host loopback only because cloudflared itself runs on the host.

> **Note:** Grafana (port 3000) binds to `0.0.0.0:3000` and **is** reachable from other machines on your network. Grafana requires login (`admin` / `GRAFANA_PASSWORD` from `.env`) and does not expose inference data — but if your LAN is untrusted, restrict it with a firewall rule or set `GF_SERVER_HTTP_ADDR=127.0.0.1` in `docker-compose.yml`.
