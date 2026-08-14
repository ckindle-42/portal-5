---
id: unit-known-limitations-comfyui-cross-model-family-memory-exhaustion-apple-silicon
kind: what
title: "KNOWN_LIMITATIONS \u2014 ComfyUI Cross-Model-Family Memory Exhaustion (Apple\
  \ Silicon)"
sources:
- type: code
  path: portal/modules/media/tools/_admission.py
- type: code
  path: tests/uat/lifecycle.py
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.664421
updated_at: 1784946220.664421
---

- **Description**: ComfyUI on MPS does not reliably evict a previously-loaded model's weights when a new workflow loads a different model family in the same long-running process. Observed live: a Wan2.1-NSFW 14B video job following a Flux image job in the same process drove swap into a full system lockup, and a tiny 9-frame/5-step wan21-nsfw job still exhausted nearly the whole 64GB unified pool. The 14B backend's real peak (diffusion activation and buffer overhead) runs well above its static on-disk weight size, regardless of frame count.
- **Impact**: Chaining image generation and large video generation, or switching between very different model families, without restarting ComfyUI in between risks a full system lockup on 64GB unified-memory Apple Silicon. The wan21-nsfw backend should be treated as needing the whole machine, not just its weight size.
- **Mitigation**: Tier 1 pre-flight admission control is implemented in `portal/modules/media/tools/_admission.py` (`admit()`); its `MEDIA_MODEL_MEMORY_GB` map sets `video:wan21-nsfw` to 55.0 GB (not the ~39GB weight size) to reflect the observed real peak, and the comment there documents the tiny-job lockup incident. Restart ComfyUI between large model-family switches regardless; the service runs as a launchd agent named `com.portal5.comfyui` (see `tests/uat/lifecycle.py`). A shared cross-engine broker with Ollama is explicitly not built.

## Why

ComfyUI's single long-running MPS process is where model-family switching accumulates memory, and the measured peak of the 14B video backend far exceeds its weight file size, so static size is a dangerously misleading admission input. The admission map hard-codes the observed 55GB figure with the incident comment attached, making the operational truth visible to any future edit that might lower the estimate.
