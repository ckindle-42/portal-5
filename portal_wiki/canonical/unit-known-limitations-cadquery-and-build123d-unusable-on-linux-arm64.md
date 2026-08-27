---
id: unit-known-limitations-cadquery-and-build123d-unusable-on-linux-arm64
kind: what
title: "KNOWN_LIMITATIONS — CadQuery and build123d on linux/arm64 (RESOLVED)"
sources:
- type: code
  path: Dockerfile.mcp
- type: code
  path: portal/modules/cad/PLATFORM.md
- type: code
  path: portal/modules/cad/tools/capabilities.py
- type: code
  path: portal/modules/cad/tools/cad_render_mcp.py
claims: []
confidence: high
tags:
- docs
- verified-v1
- resolved
created_at: 1784946220.660835
updated_at: 1787845000.0
---

- **ID**: P5-CAD-ARM64-001
- **Status**: RESOLVED (TASK_CAD_MODULE_OVERHAUL_V1 Phase 0, 2026-08-27). See
  `portal/modules/cad/PLATFORM.md` for the full empirical record.
- **Original claim (now known wrong)**: "CadQuery and build123d both require
  OCP (OpenCASCADE Python bindings), which has no pre-built wheels for
  `linux/arm64` — cannot install on arm64, use OpenSCAD only." This was a
  **pip-wheel artifact**, not a platform ceiling: it was true for *pip*
  wheels of OCP as of early 2024, but conda-forge's `ocp`/`occt` packages
  ship for `linux-aarch64` and `osx-arm64` (also linux-64/osx-64/win-64).
- **Resolution**: A micromamba/conda-forge layer in `Dockerfile.mcp` installs
  `cadquery`/`build123d`/`ocp` on the arm64 MCP image. Verified empirically on
  an osx-arm64 host: `occt-7.8.1`/`ocp-7.8.1.2`/`cadquery-2.7.0`/
  `build123d-0.9.1` installed cleanly, all imported, and a CadQuery box
  exported to a valid STL. `portal.modules.cad.tools.capabilities.
  cad_capabilities()` now probes `cadquery`/`build123d`/`ocp`/`step_read` at
  runtime instead of hardcoding platform assumptions, and `convert_cad`'s
  STEP path gates on that probe.
- **Do not reinstate** the "no arm64 wheels, OpenSCAD only" wording — it is
  factually wrong regardless of pip's continued arm64 gap. If a future
  session hits a *different* install failure, record the specific new
  failure as its own entry rather than reviving this one.
- **Residual verification note**: the empirical check above ran in a
  throwaway micromamba env on the host, proving package resolution and
  import; independently confirming the same result inside the rebuilt
  `Dockerfile.mcp` container image (via its `/capabilities` route) is
  tracked as a follow-up in `PLATFORM.md`, not yet re-verified as of this
  entry's `updated_at`.

## Why

The original register entry existed to stop CadQuery/build123d from being
silently re-added in a way that would build on x86 CI and fail on Apple
Silicon. That risk is now inverted: OCP genuinely works on arm64 via
conda-forge, and the residual risk is a future reader trusting the old
"impossible" framing and never trying. Keeping this entry (marked resolved,
with the original wrong claim preserved) rather than deleting it prevents
that regression in belief, while the still-open residual-verification item
keeps the record honest about what was proven where.
