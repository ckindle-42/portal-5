---
id: unit-HOWTO-comfyui-mcp-bridge-health-from-inside-container
kind: why
title: "HOWTO \u2014 ComfyUI MCP bridge health (from inside container):"
sources:
- type: design
  path: docs/HOWTO.md
  section: 'ComfyUI MCP bridge health (from inside container):'
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.844864
updated_at: 1783195000.844864
---

docker exec portal5-mcp-comfyui python3 -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8910/health').read().decode())"
```

---
