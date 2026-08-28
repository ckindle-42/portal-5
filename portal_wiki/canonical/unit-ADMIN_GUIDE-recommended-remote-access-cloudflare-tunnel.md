---
id: unit-ADMIN_GUIDE-recommended-remote-access-cloudflare-tunnel
kind: why
title: "ADMIN_GUIDE \u2014 Recommended remote access: Cloudflare Tunnel"
sources:
- type: code
  path: launch.sh
- type: code
  path: config/cloudflared/config.yml.example
- type: code
  path: .env.example
claims: []
confidence: high
tags:
- ADMIN_GUIDE
- docs
- verified-v1
created_at: 1783195000.813865
updated_at: 1783195000.813865
---

Recommended remote access is a Cloudflare Tunnel pointed only at Open WebUI on `:8080` — a single catch-all rule, no path routing (`config/cloudflared/config.yml.example`). Set three things in `.env`: `ENABLE_REMOTE_ACCESS=true`, `PORTAL_PUBLIC_URL=https://portal.example.com` (the address users type), and `OWUI_API_KEY` (an Open WebUI `sk-` key from Settings → Account → API Keys).

Every generator — speech, music, 3D, documents, spreadsheets, images, transcripts — writes its file locally, then publishes it through Open WebUI's files API via `portal.platform.mcp_host.owui_files.publish_file`. Chat gets one link shape, `${PORTAL_PUBLIC_URL}/api/v1/files/{id}/content/{name}`, served on `:8080` and authorised by the viewer's existing session cookie. No MCP serves files, no per-service ports, no ingress rules. The tunnel can run on any host. With `OWUI_API_KEY` unset a generator returns an error instead of a dead link.

## Why

One publish path through Open WebUI keeps the external surface a single hostname to a single port: nothing but `:8080` is ever exposed, file access rides the UI's own auth, and adding a new generator needs no tunnel or firewall change. Earlier builds served files from each MCP's own port behind per-path ingress rules; consolidating onto the files API removed that entirely.
