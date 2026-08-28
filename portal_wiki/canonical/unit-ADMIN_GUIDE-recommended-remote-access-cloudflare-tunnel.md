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

Recommended remote access is a Cloudflare Tunnel pointed only at Open WebUI on `:8080`. Set `ENABLE_REMOTE_ACCESS=true`, `PORTAL_PUBLIC_URL=https://portal.example.com`, and `OWUI_API_KEY` (an Open WebUI `sk-` key from Settings → Account). With the key set, the media MCPs publish each generated file through Open WebUI's own files API and hand chat a `${PORTAL_PUBLIC_URL}/api/v1/files/{id}/content` link — served on `:8080`, authorised by the viewer's existing session, needing no extra ingress rule and no exposed MCP port. The tunnel can run on any host; only these three variables are set here.

Fallback, when `OWUI_API_KEY` is unset: the MCPs emit per-service localhost URLs and `launch.sh` derives `MUSIC_PUBLIC_URL`, `TTS_PUBLIC_URL`, `VIDEO_PUBLIC_URL`, `CAD_RENDER_PUBLIC_URL`, and `COMFYUI_PUBLIC_URL` from `PORTAL_PUBLIC_URL`. That path needs the tunnel to also route `/files/{music,tts,models3d}/*` to ports 8912/8916/8926 and a ComfyUI hostname to 8188 — the reference rules in `config/cloudflared/config.yml.example`.

## Why

Routing generated files back through Open WebUI keeps the tunnel a single hostname to a single port: nothing but `:8080` is ever exposed, and file access rides the same auth as the rest of the UI. The per-MCP `/files/*` path predates the files-API route and stays only as a no-API-key fallback.
