---
id: unit-comfyui-setup-step-2-export-comfyui-workflow-templates
kind: what
title: "COMFYUI_SETUP \u2014 Step 2 \u2014 Export ComfyUI workflow templates"
sources:
- type: doc
  path: docs/COMFYUI_SETUP.md
  commit: 05e42ec2
  section: "Step 2 \u2014 Export ComfyUI workflow templates"
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.5566778
updated_at: 1784946220.5566778
---

`wan22-t2v-a14b` and `wan22-ti2v-5b` already have real (non-stub) workflow dicts in
`portal/modules/media/tools/video_mcp.py` — no export needed for those two. Only
`wan22-animate-14b` and `wan22-s2v-14b` remain stubs; for those, export via ComfyUI:

1. Open ComfyUI → Workflow → Browse Templates → Video
2. Load the template ("Wan2.2-Animate-14B", "Wan2.2-S2V-14B")
3. Verify the model loads and runs a test prompt
4. Export as JSON and use the node graph to populate the corresponding `_WAN22_*_WORKFLOW` dict in `portal/modules/media/tools/video_mcp.py`

Calling `wan22-animate-14b` or `wan22-s2v-14b` before that export will raise a `RuntimeError`
with instructions. `wan22-ti2v-5b` requires an `image_url` start-frame (image-to-video, not
pure text-to-video) — `wan22-t2v-a14b` does not.

**Memory warning:** on Apple Silicon, ComfyUI does not reliably evict a previously-loaded
model's weights when a new workflow loads a different model family. Loading Flux/SDXL
(~7–27GB) and then a Wan 14B video model back-to-back in the same ComfyUI process without a
restart between them can exhaust unified memory and swap simultaneously (observed twice:
swap at 66.7GB/67.6GB used, system-locking, and separately a *tiny* job crashing free RAM
from ~45GB to ~60MB — the 14B backend's real peak usage runs well above its ~39GB on-disk
weight size, close to the entire 64GB pool regardless of frame count) — restart ComfyUI
(`launchctl kickstart -k gui/$(id -u)/com.portal5.comfyui`) between large model-family
switches. `TASK_VRAM_ADMISSION_V1` (Slice 7) added a pre-flight admission check
(`portal/modules/media/tools/_admission.py`) that refuses an oversized job with a structured
error before it OOMs — see `unit-fact-media-memory-budget` / `unit-HOWTO-media-memory-and-
launch-order`; it does not replace restarting ComfyUI between families (Tier 2 cross-engine
coordination with Ollama is explicitly not built).
