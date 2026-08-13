---
id: unit-comfyui-setup-download-models
kind: what
title: "COMFYUI_SETUP \u2014 Download Models"
sources:
- type: code
  path: scripts/lib/services.sh
last_generated_commit: 75c5054f791636f367b62a1776bcc9f631794766
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.553596
updated_at: 1784946220.553596
---

The supported model download command is `pull-qwen-image`, implemented by
`_launch_pull_qwen_image` in `scripts/lib/services.sh`. It bootstraps the
`huggingface_hub` CLI when absent, then pulls the Qwen-Image checkpoints verified
on Apple Silicon MPS into ComfyUI's flat model layout — the T2I diffusion model,
the edit-2509 model, the shared FP8-scaled text encoder, the VAE, and the
Lightning distillation LoRA — skipping any file already present. The legacy
`download-comfyui-models` alias is retired: `_launch_download_comfyui_models`
exits with an error explaining that the monolithic downloader was deleted and
pointing to the family commands. Video models are not part of this set.

## Why

A single downloader script could not stay current across model families whose
sources and verification differ, so it was replaced by per-family handlers keyed
to what each family actually needs. Keeping the dead alias registered but failing
loudly with a pointer preserves CLI compatibility while forcing the operator to
the command that works for their target family.
