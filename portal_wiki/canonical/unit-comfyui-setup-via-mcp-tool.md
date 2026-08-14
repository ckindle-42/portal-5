---
id: unit-comfyui-setup-via-mcp-tool
kind: what
title: "COMFYUI_SETUP \u2014 Via MCP tool"
sources:
- type: code
  path: config/portal.yaml
- type: code
  path: portal/modules/media/tools/comfyui_mcp.py
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.5584798
updated_at: 1784946220.5584798
---

The image capability is consumed as MCP tools on the `portal-comfyui` bridge at
the reserved port. The fleet table registers the service as pipeline-callable and
IDE-visible, and the tool manifest in `comfyui_mcp.py` enumerates the image
operations — blocking generation, asynchronous submission with a job id,
status lookup, recent-image retrieval, and workflow listing. No video tool exists
on this service, and the separate video bridge is absent from the fleet, so the
only media tools an agent can invoke are image generation and its follow-ups.

## Why

Tool advertisement is controlled by the fleet registration, not by the code that
implements the tools: a manifest that lists operations means nothing until the
service appears in the fleet table with pipeline exposure on. That is why image
tools are callable while the fully implemented video tools are invisible.
