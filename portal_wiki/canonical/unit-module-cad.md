---
id: unit-module-cad
kind: mixed
title: "CAD Module \u2014 OpenSCAD/CadQuery 3D model generation"
sources:
- type: code
  path: portal/modules/cad/tools/cad_render_mcp.py
- type: code
  path: portal/modules/cad/tools/capabilities.py
- type: code
  path: portal/modules/cad/tools/scad_emitter.py
- type: code
  path: portal/modules/cad/tools/mesh_validator.py
- type: code
  path: portal/platform/wiki/adapters/modules.py
- type: code
  path: config/portal.yaml
claims:
- probe: modules.enabled
  contains: cad
confidence: high
tags:
- cad
- module
- verified-v1
created_at: 1783821386.7899158
updated_at: 1787845000.0
---

# CAD Module — OpenSCAD/CadQuery 3D model generation

## Tools

`portal.modules.cad.tools.cad_render_mcp` — the CAD render MCP server,
registered as `cad_render` in `config/portal.yaml` `mcp_fleet:` on port
8926. It is pipeline-exposed only (`expose_to_pipeline: true`,
`expose_to_ide: false`), so its tools reach workspace personas but not the
IDE. Four tools: `render_openscad`, `render_mesh`, `convert_cad`, and
`generate_scad`.

## generate_scad — constrained structured intermediate (TASK_CAD_MODULE_OVERHAUL_V1)

The model does not compute 3D coordinates. It emits a JSON geometry
description against `config/inference/cad_geometry_schema.json`, and
`portal.modules.cad.tools.scad_emitter` (a deterministic, no-LLM emitter
using a restricted AST arithmetic evaluator — not `eval()`) owns all
coordinate-frame math and CSG ordering:

- **Tier A (preferred)** — feature-level vocabulary: a `base` primitive
  plus `holes`/`pockets`/`standoffs`/`ribs`/`bosses`/`shell`/`pattern`,
  each positioned by face + semantic anchor + offset, never a raw 3D
  vector. "An M3 hole on the top face, 5mm from each end" — the emitter
  resolves the translate/rotate, not the model.
- **Tier B (bounded escape hatch)** — a constrained CSG subtree
  (primitives, translate/rotate/scale, boolean ops, extrudes) for
  geometry the feature vocabulary can't express yet; parameter
  references still resolve through the emitter.

`generate_scad` is one call: validate JSON → emit SCAD → compile →
mesh-validate → render PNG → (on failure) auto-retry. It is the primary
tool in `auto-cad`'s `system_prompt_append`; `render_openscad` (raw SCAD)
remains the fallback for trivial single-primitive parts.

## Mesh validation

`portal.modules.cad.tools.mesh_validator.validate_mesh()` is the shared
validation surface for all three render tools (`render_openscad`,
`render_mesh`, `generate_scad`): watertight, volume, bounding box,
face/vertex counts, and a machine-readable `problems[]` list
(`empty_geometry` / `non_watertight` / `degenerate_faces`) plus a
`printable` flag. `problems[]` is what the self-correcting loop keys off.

## Self-correcting feedback loop (both layers)

`classify_openscad_error()` categorizes OpenSCAD compile stderr
(syntax/undefined-variable/empty-geometry/non-manifold/timeout) with an
actionable one-line suggestion. Inside `generate_scad`:

- **Layer 1 — tool auto-retry**: up to `max_retries` (default 2), the
  tool re-emits and re-compiles applying ONLY deterministic,
  design-intent-preserving repairs (missing `$fn`, epsilon
  de-coincidence for a non-manifold coincident face). Anything requiring
  judgment is not auto-repaired.
- **Layer 2 — model re-call**: `attempts`, `retry_log`, `validation`, and
  `problems` are returned so the workspace model can inspect and issue a
  corrected `generate_scad` call if the tool's own retries didn't reach
  `printable: true`.

## Workspaces

- `auto-cad` — 3D model generation for CAD / 3D-printing design, routed to
  the module's workspaces by the `module:` tag on the portal.yaml entry.
  Runs `qwen3-coder:30b-a3b-q4_K_M-ctx16k` at `context_limit: 16384`
  (bumped from ctx8k — 8k was too tight for Tier-A JSON payloads and the
  multi-turn revision loop, which carries prior SCAD + error context
  across retries).

## Personas

- `caddesigner` (`config/personas/caddesigner.yaml`) — renamed from
  `cadquerydesigner`; the persona forbids CadQuery and uses OpenSCAD
  exclusively, so the old slug was a vestige. Historical bench results
  keep the old slug (immutable).
- `printabilityengineer` (`config/personas/printabilityengineer.yaml`) —
  DfAM engineer persona; also updated with `generate_scad` Tier-A
  guidance.

Both personas' hard constraints now state the platform reality
capability-conditionally rather than asserting CadQuery/build123d are
unavailable — see Platform tiers below.

## Platform tiers

See `portal/modules/cad/PLATFORM.md`. `portal.modules.cad.tools.
capabilities.cad_capabilities()` probes what's actually importable at
runtime (`openscad`, `trimesh`, `cadquery`, `build123d`, `ocp`, `cuda`)
rather than hardcoding a platform → capability mapping, and is exposed
via a `/capabilities` MCP route. The arm64/OSX tier is built to the
fullest: OpenSCAD + trimesh + CadQuery/build123d/OCP via conda-forge
(a micromamba layer in `Dockerfile.mcp`). `convert_cad`'s STEP
read/write path gates on `cad_capabilities()["step_read"]`. The x86/CUDA
tier (`Dockerfile.mcp.x86`) is a present-but-UNBUILT stub for the later
dual-platform (P40) focus — its genuine addition is CUDA-class model
execution, not OCP, which is already available on both tiers. See
`unit-known-limitations-cadquery-and-build123d-unusable-on-linux-arm64`
for the retired claim this overturns.

## Module State

```yaml
enabled: true
```

## Why

This is a live-config module unit, not a description: the fenced
`enabled:` value is read by `portal/platform/wiki/adapters/modules.py`
(`_unit_enabled_state`) to decide whether `auto-cad` routes and whether
`cad_render` launches in the MCP fleet, so flipping it is a real state
change gated by the CLI write-back (`writeback_module.py`). The unit is
the toggle's single source of truth, and re-grounding it to the adapter
plus the module's own tool code keeps the toggle honest against the code
it actually controls.
