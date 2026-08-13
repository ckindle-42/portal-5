---
id: unit-comfyui-setup-step-2-export-comfyui-workflow-templates
kind: what
title: "COMFYUI_SETUP \u2014 Step 2 \u2014 Export ComfyUI workflow templates"
sources:
- type: code
  path: portal/modules/media/tools/video_mcp.py
- type: code
  path: config/portal.yaml
last_generated_commit: 75c5054f791636f367b62a1776bcc9f631794766
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.5566778
updated_at: 1784946220.5566778
---

There is no workflow-template export step in the supported setup. The Wan 2.2
graphs are hand-authored dictionaries in `video_mcp.py` — the `WAN22_WORKFLOWS`
registry keys t2v-a14b, ti2v-5b, animate-14b, and s2v-14b — with node layouts
mirroring ComfyUI's official reference JSON rather than imported templates. The
compose file mounts a `workflows` directory into the engine read-only, but no
such directory ships in the repository. The video service is also absent from the
`config/portal.yaml` fleet, so even exported templates would have no consumer.

## Why

Defining workflows as code instead of exported JSON keeps them version-controlled
and reviewable with the MCP that executes them, and it means no manual export
step can fall out of sync with the code. The empty mount and missing fleet entry
are the concrete markers that this step has no operated target.
