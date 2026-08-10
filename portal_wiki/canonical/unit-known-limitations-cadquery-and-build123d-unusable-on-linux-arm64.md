---
id: unit-known-limitations-cadquery-and-build123d-unusable-on-linux-arm64
kind: what
title: "KNOWN_LIMITATIONS \u2014 CadQuery and build123d Unusable on linux/arm64"
sources:
- type: code
  path: Dockerfile.mcp
- type: code
  path: config/portal.yaml
- type: code
  path: portal/modules/cad/tools/cad_render_mcp.py
last_generated_commit: 956ee226e319e701e3605c9de6950bfa437a56f0
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.660835
updated_at: 1784946220.660835
---

- **ID**: P5-CAD-ARM64-001
- **Description**: CadQuery and build123d both require OCP (OpenCASCADE Python bindings), which has no pre-built wheels for `linux/arm64`. `Dockerfile.mcp` documents this: the code-CAD dependency comment states CadQuery/build123d cannot be installed on `linux/arm64` without a source build, so only `trimesh[easy]`, `pyrender`, and `numpy-stl` are installed.
- **Impact**: Python-native parametric CAD (`.box()`, `.extrude()` style) is unavailable inside the MCP containers. The `auto-cad` workspace in `config/portal.yaml` uses OpenSCAD instead, which runs headlessly with no platform restriction, and notes the OCP arm64 limitation in its own description.
- **Mitigation**: Use OpenSCAD via the `render_openscad` tool (exposed by `portal/modules/cad/tools/cad_render_mcp.py`) for parametric geometry. Use `trimesh` for procedural mesh manipulation.
- **Do not re-add** `cadquery` or `build123d` to `Dockerfile.mcp` without first verifying an arm64 wheel exists — the build would silently succeed on x86 CI and fail on this hardware.

## Why

The MCP CAD container must stay buildable on Apple Silicon hosts, and OCP's missing `linux/arm64` wheel makes both libraries a hard build failure there. Choosing OpenSCAD as the primary path keeps parametric geometry available without a multi-hour source compile, and the comment in `Dockerfile.mcp` records the constraint at the exact place a future dependency edit would otherwise ignore it.
