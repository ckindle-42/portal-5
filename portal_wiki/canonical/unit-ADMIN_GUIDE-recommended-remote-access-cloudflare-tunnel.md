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

Recommended remote access is a Cloudflare Tunnel: `cloudflared` runs on the host and merges the reference ingress from `config/cloudflared/config.yml.example` into its own config. The rules route `/files/{music,tts,models3d}/*` to ports 8912/8916/8926 and a ComfyUI hostname to 8188 before the catch-all to 8080. Remote media links need `ENABLE_REMOTE_ACCESS=true` and `PORTAL_PUBLIC_URL=https://portal.example.com`; `launch.sh` derives `MUSIC_PUBLIC_URL`, `TTS_PUBLIC_URL`, `VIDEO_PUBLIC_URL`, `CAD_RENDER_PUBLIC_URL`, and `COMFYUI_PUBLIC_URL` from it and the MCPs emit those into chat. The tunnel does not have to run on this machine; only `PORTAL_PUBLIC_URL` is set here, and the tunnel host handles the `/files/*` ingress routing. Without `PORTAL_PUBLIC_URL` the MCPs fall back to localhost URLs that a remote browser cannot resolve.

## Why

cloudflared on the host is the chosen remote path because it reaches host-loopback services without changing any bindings, and its ingress is path-scoped so only media files escape the machine. That keeps the tunnel as the single external surface instead of opening the full API plane, which is the security property the whole remote-access story is built on.
