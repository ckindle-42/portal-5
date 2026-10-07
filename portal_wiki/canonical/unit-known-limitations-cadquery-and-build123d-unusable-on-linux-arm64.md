---
id: unit-known-limitations-cadquery-and-build123d-unusable-on-linux-arm64
kind: what
title: "KNOWN_LIMITATIONS — CadQuery and build123d on linux/arm64 (RESOLVED)"
sources:
- type: code
  path: Dockerfile.cad
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
- **Resolution**: pip-installed arm64 wheels in the dedicated `Dockerfile.cad`
  image: `build123d==0.11.1` (pulls `cadquery-ocp-novtk`, which ships
  `manylinux_2_28_aarch64` and `macosx_11_0_arm64`) and `build123d-mcp==0.3.90`.
  The earlier conda-forge/micromamba layer in `Dockerfile.mcp` is **gone** — it
  was only needed while pip had no arm64 OCP wheels. CadQuery is intentionally
  not installed (its OCP variant conflicts with build123d's). `capabilities.py`
  probes `build123d`/`ocp`/`step_read` (and the live engine) at runtime instead
  of hardcoding platform assumptions.
- **Do not reinstate** the "no arm64 wheels, OpenSCAD only" wording — it is
  factually wrong regardless of pip's continued arm64 gap. If a future
  session hits a *different* install failure, record the specific new
  failure as its own entry rather than reviving this one.
- **In-container verification (2026-10-06)**: image `Architecture` = `arm64`,
  container `uname -m` = `aarch64`; `build123d 0.11.1`, `vtk 9.7.1`, OCP
  `OCP.cpython-311-aarch64-linux-gnu.so`, `build123d-mcp 0.3.90`; the eight gauntlet
  oracle parts all grade PASS in the container (`machine=aarch64`); `/capabilities`
  reports `build123d: true`, `ocp: true`, `engine: true`, `arch: aarch64`. The
  host (macOS arm64) passes the same oracles. This closes the residual-verification
  item the original entry carried.

## Why

The original register entry existed to stop CadQuery/build123d from being
silently re-added in a way that would build on x86 CI and fail on Apple
Silicon. That risk is now inverted: OCP genuinely works on arm64 via pip
wheels, and the residual risk is a future reader trusting the old
"impossible" framing and never trying. Keeping this entry (marked resolved,
with the original wrong claim preserved) rather than deleting it prevents
that regression in belief, while the in-container evidence above keeps the record honest about what was
proven where.
