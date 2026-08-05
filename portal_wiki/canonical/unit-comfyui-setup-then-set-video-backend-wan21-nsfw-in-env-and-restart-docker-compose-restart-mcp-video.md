---
id: unit-comfyui-setup-then-set-video-backend-wan21-nsfw-in-env-and-restart-docker-compose-restart-mcp-video
kind: what
title: "COMFYUI_SETUP \u2014 Then set VIDEO_BACKEND=wan21-nsfw in .env and restart:\
  \ docker compose restart mcp-video"
sources:
- type: code
  path: deploy/portal-5/docker-compose.yml
- type: code
  path: portal/modules/media/tools/video_mcp.py
last_generated_commit: f28832a459fb834ed6696f953f9955694b962483
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.5550752
updated_at: 1784946220.5550752
---

Do not perform this procedure. The `mcp-video` service is gated behind the video
profile, so a plain compose restart of that container in a default stack is a
no-op, and the fleet table does not advertise it regardless. The `VIDEO_BACKEND`
variable still exists in the compose environment with a wan22 default, and
`.env.example` mirrors that default; a wan21-nsfw value selects a legacy backend
in `video_mcp.py` with an admission budget far above its on-disk weight, but no
supported workflow leads an operator to set it. The instruction is archival and
contradicts the current operating posture.

## Why

Documenting the obsolete procedure is necessary so readers understand why it must
not be followed: the env var and backend code are still present, and only the
registration and profile gating make them inert. Naming that gap prevents an
operator from resurrecting a broken lane by following stale instructions.
