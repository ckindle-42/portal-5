---
id: unit-known-limitations-comfyui-model-download-commands-are-broken
kind: what
title: "KNOWN_LIMITATIONS \u2014 Legacy ComfyUI Model Download Command Is Retired"
sources:
- type: code
  path: scripts/lib/services.sh
- type: code
  path: launch.sh
- type: code
  path: portal/modules/media/tools/comfyui_mcp.py
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.663956
updated_at: 1784946220.663956
---

- **Description**: The legacy `./launch.sh download-comfyui-models` command no longer downloads models. `_launch_download_comfyui_models` in `scripts/lib/services.sh` exits with an error explaining that the standalone download script it once called was removed (2026-05-23) and pointing to the family-specific commands `pull-wan22` and `pull-qwen-image`. The command still appears in the `launch.sh` usage string for compatibility.
- **Resolution**: `_launch_pull_qwen_image` in `scripts/lib/services.sh` downloads the Qwen-Image checkpoint set verified on Apple Silicon MPS (T2I FP8, Edit-2509 FP8, shared text encoder/VAE, Lightning LoRA) into ComfyUI's flat `models/{diffusion_models,text_encoders,vae,loras}/` layout. `_launch_pull_wan22` downloads the Wan 2.2 TI2V-5B/S2V-14B/T2V-A14B set; video operation remains shelved even though the archival pull command exists.
- **Remaining impact**: Operators must use the explicit family command instead of the retired alias. Separately, `flux-uncensored` still has no verified working checkpoint source; the media MCP references a `Flux_v8-NSFW.safetensors` filename in `portal/modules/media/tools/comfyui_mcp.py`.
- **Operator action**: Run `./launch.sh pull-qwen-image` for the supported image set. Do not treat `pull-wan22` as enabling video operation; see the Wan 2.2 fp8 scaled-checkpoint limitation.

## Why

The monolithic download script was removed in favor of per-family handlers because the checkpoint sources and verification differ per model family, and a single script could not stay current across all of them. Keeping the dead alias registered but failing loudly with a pointer preserves CLI compatibility while forcing the operator to the command that actually works for their target family.
