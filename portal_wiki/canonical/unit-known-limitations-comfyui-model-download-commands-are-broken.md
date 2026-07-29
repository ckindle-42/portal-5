---
id: unit-known-limitations-comfyui-model-download-commands-are-broken
kind: what
title: "KNOWN_LIMITATIONS \u2014 ComfyUI Model Download Commands Are Broken"
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  commit: 05e42ec2
  section: ComfyUI Model Download Commands Are Broken
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.663956
updated_at: 1784946220.663956
---

- **Description**: `./launch.sh download-comfyui-models` calls `scripts/download_comfyui_models.py`, deleted in commit `ea864cf` ("superseded by pull-wan22 / pull-qwen-image commands in launch.sh") — but neither `pull-wan22` nor `pull-qwen-image` was ever implemented; both were advertised in `launch.sh --help` with no case handler. Found during Slice P media bring-up (`TASK_MEDIA_BRINGUP_V1`).
- **Update (2026-07-29)**: `pull-wan22` is now implemented (`scripts/lib/services.sh:_launch_pull_wan22`) and live-verified for TI2V-5B, S2V-14B, and T2V-A14B model downloads. **Video generation itself is shelved regardless — see `unit-known-limitations-wan22-fp8-scaled-checkpoints-crash-on-apple-silicon-mps`.** `download-comfyui-models` now exits with a clear pointer instead of `ModuleNotFoundError`. `pull-qwen-image` is still unimplemented (image generation, tracked separately — not shelved).
- **Impact**: No `launch.sh` subcommand can download Qwen-Image models yet. Separately, the `flux-uncensored` image backend's expected checkpoint (`Flux_v8-NSFW.safetensors`) has no known working source — the old script's repo (`enhanceaiteam/Flux-Uncensored-V2`) 404s, and no other reference to that filename exists in the codebase.
- **Mitigation**: Use `./launch.sh pull-wan22` for Wan 2.2 model downloads (though see the fp8/MPS unit above before relying on the output — most of what it downloads doesn't currently run on Apple Silicon). Download Qwen-Image directly with `hf download` until `pull-qwen-image` is implemented — see `docs/COMFYUI_SETUP.md#download-models`.
