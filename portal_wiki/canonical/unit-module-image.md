---
id: unit-module-image
kind: mixed
title: "Image Module — MLX-native image generation (MFLUX)"
sources:
- type: code
  path: portal/modules/media/tools/mflux_mcp.py
- type: code
  path: portal/platform/wiki/adapters/modules.py
- type: code
  path: config/portal.yaml
claims:
- probe: modules.disabled
  contains: image
confidence: high
tags:
- image
- module
---

# Image Module — MLX-native image generation (MFLUX)

## Tools

`mflux_mcp` (:8933) — a headless host-MLX wrapper over the `mflux-generate`
CLI (MLX-native FLUX port for Apple Silicon). Exposes `generate_image`
(text-to-image: schnell / z-image / klein / qwen-image / dev) and
`edit_image` (qwen-image-edit instruction editing, or plain img2img).
It replaced the removed ComfyUI image path — the tool names are deliberately
identical so the image workspaces repoint with a backend swap, not a
tool-rename cascade.

## Workspaces

- `auto-image` — image creation

## Module State

The switch is `modules.image.enabled` in `config/portal.yaml` (`portal module enable|disable` writes it). This unit documents the switch; it does not hold it.

## Why

Image generation is carved out of the `media` toggle into its own module so
a tight-footprint box can disable image generation (a ~25GB MLX working set)
while keeping speech and transcription. The module gates the `mflux` fleet
id and the `auto-image` workspace, both derived from their `module: image`
tag in `config/portal.yaml`. The shipped switch is
`modules.image.enabled: false`. A missing key falls back to
`DEFAULT_ENABLED_MODULES` (on).
