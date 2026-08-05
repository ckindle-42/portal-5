---
id: unit-ADMIN_GUIDE-check-which-models-ollama-currently-has-loaded
kind: why
title: "ADMIN_GUIDE \u2014 Check which models Ollama currently has loaded"
sources:
- type: code
  path: portal/platform/mcp_host/pipeline_mcp.py
- type: code
  path: .env.example
last_generated_commit: 3d2aca98eaf073d6bc9028a05b44d5321f3f2d87
claims: []
confidence: high
tags:
- ADMIN_GUIDE
- docs
- verified-v1
created_at: 1783195000.8172958
updated_at: 1783195000.8172958
---

Ollama reports resident models through its `/api/ps` endpoint. The shell check is:

```bash
curl -s http://localhost:11434/api/ps | jq '.models[] | {name, size_vram}'
```

The port and host come from `OLLAMA_URL` (default `http://host.docker.internal:11434`). The same endpoint powers the `get_loaded_models` tool in `portal/platform/mcp_host/pipeline_mcp.py`, which returns each model's name and `vram_size_gb` — the tool is what an agent sees as `portal-pipeline get_loaded_models`.

## Why

"Which models are resident" answers the two most common operational questions at once: is the router model warm (if not, the next `auto` request cold-loads it and falls through to Layer 2), and is a large inference model squatting on unified memory at the expense of everything else. The same query is exposed to both shell and agent so operators and automation read identical state.
