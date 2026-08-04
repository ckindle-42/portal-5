---
id: unit-comfyui-setup-wan-2-2-family-v6-2-addition
kind: what
title: "COMFYUI_SETUP \u2014 Wan 2.2 Family (v6.2 addition)"
sources:
- type: code
  path: portal/modules/media/tools/video_mcp.py
- type: code
  path: deploy/portal-5/docker-compose.yml
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.555469
updated_at: 1784946220.555469
---

The Wan 2.2 family is an implementation inventory, not a service. The workflow
registry in `video_mcp.py` maps four variants: t2v-a14b is a real two-expert
graph whose fp8 checkpoints crash on MPS; ti2v-5b is a real fp16 graph that was
verified but shelved by decision; animate-14b is a stub that raises an
explanatory error when selected; s2v-14b is a real graph whose fp8 checkpoint
also crashes at dequantization. The compose profile keeps the container out of
the default start set, and the fleet table omits the video entry entirely. None
of the four variants is exposed as a supported Portal capability.

## Why

The registry is kept as a complete inventory even though only the shelving is
operational because each variant carries a different reason for being inactive —
crash, decision, or stub — and conflating them would mislead a future operator.
The stub in particular is deliberate: it raises loudly rather than silently
producing nothing.
