---
id: unit-capability-cad-render
kind: mixed
title: "CAD Render MCP \u2014 mesh rendering and CAD conversion"
sources:
- type: code
  path: config/portal.yaml
  section: mcp_fleet
- type: code
  path: portal/modules/cad/tools/cad_render_mcp.py
- type: code
  path: config/inference/tools_manifest_cad_render_mcp.json
claims: []
confidence: high
tags:
- capability
- mcp
- cad
created_at: 1788030600.446044
updated_at: 1788030600.446044
---

# CAD Render MCP — mesh rendering and CAD conversion

## What

The CAD Render MCP (`portal/modules/cad/tools/cad_render_mcp.py`, port 8926)
renders and converts CAD/mesh artifacts. It is pipeline-exposed
(`expose_to_pipeline: true`) but not IDE-exposed, so it is invoked by the
`auto-cad` workspace rather than from an editing session.

## How it's used

`render_mesh` renders a 3D model to an image; `render_openscad` compiles and
renders an OpenSCAD script; `convert_cad` converts between supported CAD/mesh
formats; `generate_scad` produces a parametric OpenSCAD source from a
description. The rendering review model is configurable through
`CAD_RENDER_REVIEW_MODEL`, letting the review step ride the model family an
operator already trusts.

## Why it exists

CAD is a niche but genuine media surface: a workspace needs to turn a model
file or a parametric script into a visual artifact and iterate on it. Keeping
it as one module with its own MCP means the heavy rendering dependencies live
in one place and the review-model knob is a single env var instead of a code
change.

## Value

The auto-cad lane produces renderable, reviewable artifacts without a GUI
round-trip — useful for 3D-print and OpenSCAD workflows where the prompt can
describe a part, see the render, and revise. The separate review model lets an
operator keep cost down on the generation step while spending quality tokens
only where the judgment matters.
