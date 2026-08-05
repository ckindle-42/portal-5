---
id: unit-comfyui-setup-step-1-pull-the-weights-opt-in-80gb-total
kind: what
title: "COMFYUI_SETUP \u2014 Step 1 \u2014 Pull the weights (opt-in, ~80GB total)"
sources:
- type: code
  path: scripts/lib/services.sh
- type: code
  path: deploy/portal-5/docker-compose.yml
last_generated_commit: f28832a459fb834ed6696f953f9955694b962483
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.5558279
updated_at: 1784946220.5558279
---

No Wan weights are required for the supported image-only setup, so step one of
the old video guide is optional. The handler `_launch_pull_wan22` remains
available and downloads the full Wan 2.2 set into the engine's flat layout — the
fp16 TI2V model, the fp8 S2V and the high/low-noise T2V expert pair, plus the
shared text encoder, VAE, and audio encoder — flattening the repackaged
repository's internal folder prefix so the engine can find the files. The set is
large and consumes disk, and nothing in the compose file starts the video service
that would use it. Running the pull does not enable video operation.

## Why

The pull command is retained for re-evaluation rather than deleted because the
shelving decision is reversible: if MPS fp8 support lands, the weights are one
command away. Keeping it explicit and archival — with the folder-flattening
handling that fixed a real download bug — preserves the path without implying the
service is operated.
