---
id: unit-readme-image-generation-downloaded-automatically-on-first-run-12-gb
kind: what
title: "README \u2014 Image generation (downloaded automatically on first run, ~12\
  \ GB)"
sources:
- type: code
  path: .env.example
- type: code
  path: deploy/portal-5/docker-compose.yml
- type: code
  path: scripts/lib/services.sh
- type: code
  path: portal/modules/media/tools/comfyui_mcp.py
- type: code
  path: scripts/gen-image.py
last_generated_commit: 75c5054f791636f367b62a1776bcc9f631794766
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.687387
updated_at: 1784946220.687387
---

Image generation runs through ComfyUI, and the default checkpoint is FLUX.1-schnell,
set by `IMAGE_MODEL=flux-schnell` in `.env.example`. The same file documents the
alternatives: `flux-dev` (about 24 GB, requires `HF_TOKEN`), `flux-uncensored`,
`sdxl`, `juggernaut-xl`, `pony-diffusion` and `epicrealism-xl`.

`IMAGE_MODEL` is consumed in `deploy/portal-5/docker-compose.yml` by the opt-in
`comfyui-model-init` service (`IMAGE_MODEL=${IMAGE_MODEL:-flux-schnell}`), which
downloads checkpoints on first start under the `docker-comfyui` profile. On the
default Apple Silicon path ComfyUI runs natively on the host, and checkpoints are
fetched with `./launch.sh pull-qwen-image` / `./launch.sh pull-wan22`
(`scripts/lib/services.sh`), which download ComfyUI-flat model files via `hf
download`. The MCP tool `generate_image` in
`portal/modules/media/tools/comfyui_mcp.py` selects the checkpoint per workflow,
and `scripts/gen-image.py` is the standalone CLI wrapper with a `--model` override.

## Why

Image checkpoints are large enough (the FLUX schnell default is roughly 12 GB)
that bundling every option into the base install would waste disk and slow first
boot. `IMAGE_MODEL` picks the default while the `pull-qwen-image` / `pull-wan22`
commands fetch specific checkpoints on demand, so the operator pays the download
cost only for the models actually used.
