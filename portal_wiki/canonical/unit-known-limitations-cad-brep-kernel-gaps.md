---
id: unit-known-limitations-cad-brep-kernel-gaps
kind: what
title: "generate_part kernel gaps vs the OpenSCAD backend (P5-CAD-BREP-KERNEL-GAP-001)"
sources:
- type: code
  path: portal/modules/cad/tools/b123d_emitter.py
- type: code
  path: portal/modules/cad/tools/part_plan.py
claims: []
confidence: high
tags:
- known-limitations
- cad
created_at: 1791300000
updated_at: 1791300000
---

- **ID**: P5-CAD-BREP-KERNEL-GAP-001
- **Status**: ACTIVE — explicit errors, no silent degradation
- **Description**: `generate_part` renders the same JSON IR as `generate_scad` on the build123d BREP kernel, with SCAD-parity gates (volume, genus, bbox on the corpus). Two feature sets are not expressible and return `error_category: "kernel_gap"` pointing the model at `cad_build`: (1) Tier-B `linear_extrude`/`rotate_extrude` escape-hatch nodes (the IR has no 2D primitives, so the SCAD form is degenerate too); (2) a base carrying both `fillets` and `chamfers` (the second operation would select the first one's blended edges). `generate_scad` is unaffected.
- **Vocabulary note**: polygon prisms, stepped/revolved bodies and L-brackets are now
  first-class bases (`prism`, `revolve`, `angle`) and are NOT gaps; they accept holes only.
  Gears, T/U shapes, multi-body assemblies, lofts, and features inside a shelled box still
  need `cad_build`.
- **Also**: the SCAD fillet envelope always rounds a box's vertical edges whatever `edges` says; the BREP backend matches that for fillets only. OCC's STL tessellation of an all-edges-filleted box can leave a few zero-area sliver triangles, so a strict watertight mesh check may flag it although the BREP solid is valid.
- **Mitigation**: write such parts with `cad_build`, or use `generate_scad`.

## Why

Failing loudly at emit time keeps the model's correction loop honest: a silent approximation would pass validation while building the wrong part, and the structured `kernel_gap` category tells the model exactly which tool to switch to instead of guessing.
