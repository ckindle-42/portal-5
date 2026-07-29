---
id: unit-known-limitations-comfyui-model-download-commands-are-broken
kind: what
title: "KNOWN_LIMITATIONS \u2014 Legacy ComfyUI Model Download Command Is Retired"
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

- **Description**: The legacy `./launch.sh download-comfyui-models` command no longer downloads models because its monolithic script was deleted in commit `ea864cf`; the handler now exits with a clear pointer to the family-specific commands.
- **Resolution (2026-07-29)**: `pull-qwen-image` and `pull-wan22` both have real handlers. `pull-qwen-image` now downloads the exact image checkpoints verified on Apple Silicon MPS: Qwen-Image-2512 plain FP8, Qwen-Image-Edit-2509 plain FP8, the shared text encoder/VAE, and the Lightning LoRA. Video generation remains shelved even though its archival pull command exists.
- **Remaining impact**: Operators must use the explicit family command instead of the retired alias. Separately, `flux-uncensored` still has no known working checkpoint source.
- **Operator action**: Run `./launch.sh pull-qwen-image` for the supported image set. Do not treat `pull-wan22` as enabling video operation; see `unit-known-limitations-wan22-fp8-scaled-checkpoints-crash-on-apple-silicon-mps`.
