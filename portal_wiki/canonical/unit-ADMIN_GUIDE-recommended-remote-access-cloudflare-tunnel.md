---
id: unit-ADMIN_GUIDE-recommended-remote-access-cloudflare-tunnel
kind: why
title: "ADMIN_GUIDE \u2014 Recommended remote access: Cloudflare Tunnel"
sources:
- type: design
  path: docs/ADMIN_GUIDE.md
  section: 'Recommended remote access: Cloudflare Tunnel'
last_generated_commit: ''
confidence: high
tags:
- docs
- ADMIN_GUIDE
created_at: 1783195000.813865
updated_at: 1783195000.813865
---


Run `cloudflared` on the host and configure ingress rules that route specific paths to the local services. The MCP servers stay loopback-only — cloudflared (running on the host, not in docker) reaches them through `127.0.0.1`. A reference ingress configuration is provided at `config/cloudflared/config.yml.example`.

To make generated media links work for remote browsers:

```
ENABLE_REMOTE_ACCESS=true
PORTAL_PUBLIC_URL=https://portal.example.com
```

`launch.sh` derives `MUSIC_PUBLIC_URL`, `TTS_PUBLIC_URL`, `VIDEO_PUBLIC_URL`, and `COMFYUI_PUBLIC_URL` from `PORTAL_PUBLIC_URL`, and the MCPs emit those into chat instead of `http://localhost:<port>/...`.

Without `PORTAL_PUBLIC_URL` set, every MCP falls back to localhost-only links — Open WebUI can still be reached remotely, but media download links inside chat won't resolve from a remote browser.
