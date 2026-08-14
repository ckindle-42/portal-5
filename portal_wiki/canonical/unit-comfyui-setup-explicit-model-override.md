---
id: unit-comfyui-setup-explicit-model-override
kind: what
title: "COMFYUI_SETUP \u2014 Explicit model override"
sources:
- type: code
  path: config/portal.yaml
- type: code
  path: portal/modules/media/tools/video_mcp.py
last_generated_commit: 41df61e0a6102275a700700e9765972f1508c4c5
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.558147
updated_at: 1784946220.558147
---

Explicit video model overrides are unreachable while video is shelved. The
`video_mcp.py` dispatch still accepts a `model` argument that selects a key from
`WAN22_WORKFLOWS` — t2v-a14b, ti2v-5b, animate-14b, s2v-14b — and the tool
documentation still lists those variants. What changed is registration:
`config/portal.yaml` removed the video entry from `mcp_fleet`, so no video tool
is advertised to the pipeline or the IDE, and the compose file gates the
`mcp-video` container behind a non-default profile. With the service never
started, no override can be exercised. Image-model overrides on the `comfyui_mcp`
service remain fully operational.

## Why

Making a tool reachable is a registration act, not a code act: the fleet table in
`config/portal.yaml` is what the pipeline and Open WebUI discover, so deleting
the video entry is what actually takes the capability away. Leaving the dispatch
and workflows intact keeps the removal reversible — one YAML line restores video
advertisement if the MPS fp8 blocker is ever resolved.
