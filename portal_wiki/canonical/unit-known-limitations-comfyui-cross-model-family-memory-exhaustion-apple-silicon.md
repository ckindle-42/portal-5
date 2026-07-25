---
id: unit-known-limitations-comfyui-cross-model-family-memory-exhaustion-apple-silicon
kind: what
title: "KNOWN_LIMITATIONS \u2014 ComfyUI Cross-Model-Family Memory Exhaustion (Apple\
  \ Silicon)"
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  commit: 05e42ec2
  section: ComfyUI Cross-Model-Family Memory Exhaustion (Apple Silicon)
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.664421
updated_at: 1784946220.664421
---

- **Description**: ComfyUI on MPS does not reliably evict a previously-loaded model's weights when a new workflow loads a different model family in the same long-running process. Observed live during Slice P: Flux (~22GB) followed by a Wan2.1-NSFW 14B video job (~39GB) in the same process, without a restart between them, drove swap to 66.7GB/67.6GB used and locked up the system (not just RAM pressure — genuine swap-thrashing). Recurred a second time during Slice 7's own live verification: a *tiny* wan21-nsfw job (9 frames, 5 steps) still crashed free RAM from ~45GB to ~60MB — the 14B backend's real peak usage (diffusion activation/buffer overhead) runs well above its static on-disk weight size (~39GB) regardless of frame count, close to the entire 64GB pool.
- **Impact**: Chaining image generation and large video generation (or switching between very different video model families) without restarting ComfyUI in between risks a full system lockup on 64GB unified-memory Apple Silicon hardware. The wan21-nsfw backend specifically should be treated as needing the *whole* machine, not just its weight size.
- **Mitigation**: Tier 0 (`unit-fact-media-memory-budget`) and Tier 1 (`portal/modules/media/tools/_admission.py`, `admit()`) pre-flight admission control landed in `TASK_VRAM_ADMISSION_V1` (Slice 7) — wan21-nsfw's estimate is set to 55GB (not the 39GB weight size) to reflect the observed real peak. Restart ComfyUI between large model-family switches regardless: `launchctl kickstart -k gui/$(id -u)/com.portal5.comfyui`. Tier 2 (shared cross-engine broker with Ollama) is explicitly not built — see the task's `[GATE: SCOPE]`.
