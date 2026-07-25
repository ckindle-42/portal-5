---
id: unit-comfyui-setup-download-models
kind: what
title: "COMFYUI_SETUP \u2014 Download Models"
sources:
- type: doc
  path: docs/COMFYUI_SETUP.md
  commit: 05e42ec2
  section: Download Models
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.553596
updated_at: 1784946220.553596
---

**`./launch.sh download-comfyui-models` is currently broken** — the script it called
(`scripts/download_comfyui_models.py`) was deleted in commit `ea864cf` ("superseded by
pull-wan22 / pull-qwen-image"), but those replacement subcommands were never implemented
in `launch.sh` (found during Slice P media bring-up, `TASK_MEDIA_BRINGUP_V1`). Until one of
them is rebuilt, download models directly with `hf download` / `huggingface-cli download`.
