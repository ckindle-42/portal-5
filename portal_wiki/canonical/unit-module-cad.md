---
id: unit-module-cad
kind: mixed
title: "CAD Module \u2014 build123d BREP primary, OpenSCAD fallback"
sources:
- type: code
  path: portal/modules/cad/tools/cad_render_mcp.py
- type: code
  path: portal/modules/cad/tools/capabilities.py
- type: code
  path: portal/modules/cad/tools/scad_emitter.py
- type: code
  path: portal/modules/cad/tools/b123d_emitter.py
- type: code
  path: portal/modules/cad/tools/part_plan.py
- type: code
  path: portal/modules/cad/tools/b123d_bridge.py
- type: code
  path: Dockerfile.cad
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

# CAD Module — build123d BREP primary, OpenSCAD fallback

## Tools

`portal.modules.cad.tools.cad_render_mcp` — the CAD render MCP server,
registered as `cad_render` in `config/portal.yaml` `mcp_fleet:` on port
8926. It is pipeline-exposed only (`expose_to_pipeline: true`,
`expose_to_ide: false`), so its tools reach workspace personas but not the
IDE. It runs from its own arm64-native image (`Dockerfile.cad`, compose
`platform: linux/arm64`) — OCP + VTK + OpenSCAD are kept out of the shared
`Dockerfile.mcp`. Eleven tools, in two groups:

- **BREP primary (build123d):** `generate_part` (JSON IR in, exact solid out)
  and six `cad_*` tools — `cad_build`, `cad_execute`, `cad_measure`,
  `cad_find_holes`, `cad_render`, `cad_finalize` — fronting an in-container
  `build123d-mcp` engine.
- **Fallback / mesh:** `generate_scad` (OpenSCAD), `render_openscad`,
  `render_mesh`, `convert_cad`.

## Backends

`part_plan.plan_part()` validates the geometry IR and does all coordinate math
once (a kernel-neutral `PartPlan`); two backends render it. `scad_emitter`
emits OpenSCAD (output pinned byte-for-byte by `tests/data/cad_scad_golden/`);
`b123d_emitter` emits a build123d algebra-mode script, checked against the SCAD
meshes for volume/genus/bbox parity. Gaps are explicit `kernel_gap` errors
(Tier-B extrudes; a base with both fillets and chamfers) that point the model at
`cad_build`.

## build123d engine bridge (`b123d_bridge.py`)

The six `cad_*` tools are a thin bridge over a loopback-only (`127.0.0.1:18123`,
not a host port) `build123d-mcp 0.3.90` HTTP engine that `cad_render_mcp`
starts at launch. The engine is spawned with an allowlisted environment and its
own import sandbox. Sessions: one isolated CAD session per pipeline request
(the request id is the handle); the bridge does LRU eviction under the engine's
session cap and retries on 503; idle sessions expire after
`CAD_B3D_IDLE_TIMEOUT_S` (default 900 s). Cross-turn continuity is carried by
the saved script/STEP, not live session state. Tool-level failures are returned
with HTTP 200 and `ok:false` so a model mistake never trips the pipeline's
circuit breaker.

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
- **Base types** — `box`, `cylinder`, and (TASK_CAD_ARM_REDEVELOP_V1) `prism`
  (regular N-gon bar: hex stock / nut / hex standoff via `across_flats` or
  `circumradius`), `revolve` (stepped/flanged/revolved body from a `[radius, z]`
  profile that includes the bore) and `angle` (L-bracket: width, depth, height,
  thickness, `inner_radius`). The new bases take holes (and patterns of holes)
  only — `prism`/`revolve` on top/bottom, `angle` on bottom (horizontal leg) and
  front (vertical leg); shell/pockets/standoffs/ribs/fillets/chamfers on them are
  explicit errors pointing at `cad_build`. Both backends render them; the
  reference IRs for the gauntlet's hex standoff, flanged bushing and L-bracket
  grade PASS on the sealed grader (`tests/unit/test_cad_ir_bases.py`).
- **Tier B (bounded escape hatch)** — a constrained CSG subtree
  (primitives, translate/rotate/scale, boolean ops, extrudes) for
  geometry the feature vocabulary can't express yet; parameter
  references still resolve through the emitter.

`generate_scad` is one call: validate JSON → emit SCAD → compile →
mesh-validate → render PNG → (on failure) auto-retry. Since
TASK_CAD_ARM_REDEVELOP_V1 it is no longer in `auto-cad`'s toolset
(`generate_part` is the same IR on the BREP kernel and is primary); it stays
registered as the OpenSCAD fallback and for historical eval arms.

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
  Runs `qwen3-coder:30b-a3b-q4_K_M-ctx32k` at `context_limit: 32768`: the
  20-tool schema set plus the system prompt is ~5.2K tokens, 31.7 % of the old
  16K window. build123d BREP primary (`generate_part`, `cad_*`), OpenSCAD only
  on explicit request.
- `bench-qwen38-cad` (module `eval`) — the dense challenger: the same toolset on
  `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k`, `think: false`. Evaluated by
  the v2 gauntlet (`tests/benchmarks/bench_cad_gauntlet_v2.py`); promotion is an
  operator decision (`PROMOTE_POLICY=confirm`).

## Personas

- `caddesigner` (`config/personas/caddesigner.yaml`) — renamed from
  `cadquerydesigner`; historical bench results keep the old slug (immutable).
  build123d-first: `generate_part` -> `cad_build` -> verify -> `cad_finalize`.
- `printabilityengineer` (`config/personas/printabilityengineer.yaml`) —
  DfAM engineer persona; treats `cad_finalize`'s BREP printability findings as
  DfAM issues to fix or justify.

## Platform

See `portal/modules/cad/PLATFORM.md`. Standing rule: native means arm64 (host
binaries/wheels, and Docker images built for `linux/arm64`); `Dockerfile.cad`
asserts `aarch64` at build time. build123d `0.11.1` + build123d-mcp `0.3.90`
are pip arm64 wheels (pinned together: build123d-mcp requires
`build123d>=0.10,<0.12`); there is no conda/micromamba layer any more.
OpenSCAD is the arm64 `openscad-nightly` with the Manifold backend
(`CAD_OPENSCAD_BACKEND=manifold`). `capabilities.cad_capabilities()` still
probes what is really present (`openscad_bin|version|backend`, `build123d`,
`ocp`, `build123d_mcp`, `arch`; `cad_status()` adds the live `engine` flag) and
is served at `/capabilities`; `convert_cad`'s STEP path gates on
`step_read`. The x86/CUDA tier (`Dockerfile.mcp.x86`) is an unbuilt stub. See
`unit-known-limitations-cadquery-and-build123d-unusable-on-linux-arm64` for the
retired claim this overturns.

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
