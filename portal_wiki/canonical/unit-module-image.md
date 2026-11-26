---
id: unit-module-image
kind: mixed
title: "Image Module \u2014 MLX-native image generation (MFLUX)"
sources:
- type: code
  path: portal/modules/media/tools/mflux_mcp.py
- type: code
  path: portal/platform/wiki/adapters/modules.py
- type: code
  path: config/portal.yaml
claims: []
confidence: high
tags:
- image
- module
---

# Image Module — MLX-native image generation (MFLUX)

## Tools

`mflux_mcp` (:8933) — a headless host-MLX wrapper over the per-family
`mflux-generate-*` CLIs (mflux >=0.24.0, MLX-native for Apple Silicon). Exposes
`generate_image` / `image_start` (text-to-image: flux2-klein 4-step default /
flux3-klein 16-step / qwen-2.1-turbo 8-step / z-image-turbo) and `edit_image`
(the family's `*-edit` binary, instruction editing with `--image-paths`).
`image_start` returns a job id immediately; `image_status(job_id, wait_s=20)` in
a later turn returns progress or the published download URL. It replaced the
removed ComfyUI image path — the tool names are deliberately identical so the
image workspaces repoint with a backend swap, not a tool-rename cascade.

## Workspaces

- `auto-image` — image creation

## Module State

The switch is `modules.image.enabled` in `config/portal.yaml` (`portal module enable|disable` writes it). This unit documents the switch; it does not hold it.

## Why

Image generation is carved out of the `media` toggle into its own module so
a tight-footprint box can disable image generation (a ~18–26GB MLX working set)
while keeping speech and transcription. The module gates the `mflux` fleet
id and the `auto-image` workspace, both derived from their `module: image`
tag in `config/portal.yaml`. The live switch lives in `config/portal.yaml` (`unit-fact-module-states`; mflux 0.24, flux2-klein default). A missing key falls back to
`DEFAULT_ENABLED_MODULES` (on).
