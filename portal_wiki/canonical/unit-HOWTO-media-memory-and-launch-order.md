---
id: unit-HOWTO-media-memory-and-launch-order
kind: why
title: Media memory and launch order
sources:
- type: design
  path: coding_task/video_work/TASK_VRAM_ADMISSION_V1.md
last_generated_commit: ''
confidence: high
tags:
- HOWTO
- media
- memory
- comfyui
created_at: 1784057635.351039
updated_at: 1784057635.351039
---

# Media memory and launch order

ComfyUI (image/video) and Ollama share the same 64GB unified-memory pool on Apple Silicon,
with **no cross-engine backpressure**: Ollama's `OLLAMA_MAX_LOADED_MODELS`/`OLLAMA_MEMORY_LIMIT`
do not govern ComfyUI, and the old MLX-proxy admission gate (retired at `3a0c58e`) never covered
media backends either. See `unit-fact-media-memory-budget` for per-backend GB estimates.

## What actually happened (2026-07-14, Slice P)

Loading Flux (~27GB: checkpoint+CLIP+VAE) and then the wan21-nsfw 14B video backend (~38GB)
back-to-back in the *same* long-running ComfyUI process, without a restart between them, drove
swap to 66.7GB/67.6GB used and locked the system — not just RAM pressure, genuine swap-thrashing.
ComfyUI on MPS does not reliably evict a prior model's weights when a new workflow loads a
different model family.

## Safe co-residency matrix

| Combination | Safe? | Why |
|---|---|---|
| Ollama small/medium model (<20GB) + ComfyUI image (Flux/SDXL) | Usually | Sums stay under ~50GB with headroom |
| Ollama large model (30GB+) + ComfyUI image | Marginal | Check free memory first; consider unloading Ollama |
| Any Ollama model + ComfyUI video (wan21-nsfw, 38GB+) | **Unsafe without care** | Video backends alone approach the 64GB ceiling |
| ComfyUI image *then* ComfyUI video, same process, no restart | **Unsafe** | ComfyUI does not evict the prior model reliably |

## Launch order (until Tier 2 cross-engine broker exists)

1. Before a large media job (especially video), check what's loaded: `curl localhost:11434/api/ps`
   (Ollama) and the target media backend's estimated GB (`unit-fact-media-memory-budget`).
2. If a large Ollama model is loaded and the media job is also large, unload the Ollama model first
   (`ollama stop <model>` or let `KEEP_ALIVE` expire) or wait for the eviction.
3. Between ComfyUI jobs that load different model families (e.g., Flux then a Wan video backend),
   restart ComfyUI: `launchctl kickstart -k gui/$(id -u)/com.portal5.comfyui`. Do not assume the
   prior model's memory was released.
4. The Tier 1 pre-flight check (`portal/modules/media/tools/_admission.py`) refuses a job with a
   structured error when the estimate plus headroom exceeds free memory — but it cannot see what
   Ollama or another ComfyUI job in flight is using beyond the free-memory snapshot at admission
   time, so steps 1-3 still matter.
