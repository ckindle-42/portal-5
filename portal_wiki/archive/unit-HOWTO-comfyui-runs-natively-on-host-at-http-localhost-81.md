---
id: unit-HOWTO-comfyui-runs-natively-on-host-at-http-localhost-81
historical: true
kind: why
title: "HOWTO \u2014 ComfyUI runs natively on host at http://localhost:8188 (not in\
  \ Docker)"
sources:
- type: design
  path: docs/HOWTO.md
  section: ComfyUI runs natively on host at http://localhost:8188 (not in Docker)
confidence: high
tags:
- docs
- HOWTO

---

curl -s http://localhost:8188/system_stats | python3 -c "import sys,json; d=json.load(sys.stdin); print('ComfyUI:', d['system']['comfyui_version'], '| MPS available:', 'mps' in [dev['type'] for dev in d['system']['devices']])"
