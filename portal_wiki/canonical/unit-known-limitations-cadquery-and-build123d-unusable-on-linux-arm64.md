---
id: unit-known-limitations-cadquery-and-build123d-unusable-on-linux-arm64
kind: what
title: "KNOWN_LIMITATIONS \u2014 CadQuery and build123d Unusable on linux/arm64"
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  commit: 05e42ec2
  section: CadQuery and build123d Unusable on linux/arm64
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.660835
updated_at: 1784946220.660835
---

- **ID**: P5-CAD-ARM64-001
- **Description**: CadQuery ≥2.4 and build123d both require `cadquery-ocp` / `ocp` (OpenCASCADE Python bindings), which has no pre-built wheels for `linux/arm64`. Installing either package in `Dockerfile.mcp` on Apple Silicon fails at build time.
- **Impact**: Python-native parametric CAD (`.box()`, `.extrude()` style) is unavailable inside the MCP containers. The `auto-cad` workspace uses OpenSCAD instead, which runs headlessly and has no platform restriction.
- **Mitigation**: Use OpenSCAD via the `render_openscad` tool for parametric geometry. Use `trimesh` (installed) for procedural mesh manipulation. If CadQuery is required in future, it must be built from source (multi-hour OCP compile) or sourced from a community arm64 wheel when one becomes available.
- **Do not re-add** `cadquery` or `build123d` to `Dockerfile.mcp` without first verifying an arm64 wheel exists — the build will silently succeed on x86 CI and fail on this hardware.

---
