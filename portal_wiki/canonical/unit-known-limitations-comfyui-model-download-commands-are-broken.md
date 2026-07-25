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

- **Description**: `./launch.sh download-comfyui-models` calls `scripts/download_comfyui_models.py`, deleted in commit `ea864cf` ("superseded by pull-wan22 / pull-qwen-image commands in launch.sh") — but neither `pull-wan22` nor `pull-qwen-image` was ever implemented; both are advertised in `launch.sh --help` with no case handler. Found during Slice P media bring-up (`TASK_MEDIA_BRINGUP_V1`).
- **Impact**: No `launch.sh` subcommand can download ComfyUI image/video models. Separately, the `flux-uncensored` image backend's expected checkpoint (`Flux_v8-NSFW.safetensors`) has no known working source — the old script's repo (`enhanceaiteam/Flux-Uncensored-V2`) 404s, and no other reference to that filename exists in the codebase.
- **Mitigation**: Download directly with `hf download` / `huggingface-cli download` — see `docs/COMFYUI_SETUP.md#download-models` for the exact working commands (flux-schnell, sdxl, wan21-nsfw). Rebuilding `pull-wan22`/`pull-qwen-image` (or restoring the deleted script) is open work.
