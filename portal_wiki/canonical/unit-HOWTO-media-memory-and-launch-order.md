---
id: unit-HOWTO-media-memory-and-launch-order
kind: why
title: Media memory and launch order
sources:
- type: code
  path: portal/modules/media/tools/_admission.py
- type: code
  path: config/portal.yaml
last_generated_commit: 64c5f5f41652bf67e97863ee1a6285289eaeea00
claims: []
confidence: high
tags:
- HOWTO
- comfyui
- media
- memory
- verified-v1
created_at: 1784057635.351039
updated_at: 1784057635.351039
---

# Media memory and launch order

ComfyUI image generation and Ollama share the same 64GB unified-memory pool on Apple Silicon,
with **no cross-engine backpressure**: Ollama's `OLLAMA_MAX_LOADED_MODELS`/`OLLAMA_MEMORY_LIMIT`
do not govern ComfyUI, and the old MLX-proxy admission gate (retired at `3a0c58e`) never covered
media backends either. See `unit-fact-media-memory-budget` for per-backend GB estimates. Video
rows in that fact-unit describe retained archival code; video service operation is shelved.

## Historical incident that established the guard (2026-07-14, Slice P)

Loading Flux (~27GB: checkpoint+CLIP+VAE) and then the wan21-nsfw 14B video
backend (static weights ~38GB) back-to-back in the *same* long-running ComfyUI
process, without a restart between them, drove
swap to 66.7GB/67.6GB used and locked the system — not just RAM pressure, genuine swap-thrashing.
ComfyUI on MPS does not reliably evict a prior model's weights when a new workflow loads a
different model family.

## Safe co-residency matrix

| Active combination | Safe? | Why |
|---|---|---|
| Ollama small/medium model (<20GB) + Qwen image/edit | Usually | Admission still checks current free memory and configured headroom |
| Ollama large model (30GB+) + Qwen image/edit | Marginal or refused | Qwen image peaks are roughly 38–60GB; unload Ollama first |
| Any video combination | N/A | Video service operation is shelved |

## Launch order (until Tier 2 cross-engine broker exists)

1. Before a large image job, check what's loaded: `curl localhost:11434/api/ps`
   (Ollama) and the target media backend's estimated GB (`unit-fact-media-memory-budget`).
2. If a large Ollama model is loaded and the media job is also large, unload the Ollama model first
   (`ollama stop <model>` or let `KEEP_ALIVE` expire) or wait for the eviction.
3. Between large ComfyUI model-family changes, restart ComfyUI:
   `launchctl kickstart -k gui/$(id -u)/com.portal5.comfyui`. Do not assume the prior
   model's memory was released.
4. The Tier 1 pre-flight check (`portal/modules/media/tools/_admission.py`) refuses a job with a
   structured error when the estimate plus headroom exceeds free memory — but it cannot see what
   Ollama or another ComfyUI job in flight is using beyond the free-memory snapshot at admission
   time, so steps 1-3 still matter.

## Why

This guidance exists because ComfyUI and Ollama share one unified-memory
pool with no cross-engine broker, so a large media job can OOM a system
that looks idle to either stack alone. The incident record and the safe
co-residency matrix are grounded in the per-backend peak estimates in
`portal/modules/media/tools/_admission.py` (mirrored from
`unit-fact-media-memory-budget`), and the launch-order steps follow the
exact remediation strings that admission check returns in its structured
refusal error. The co-residency and launch-order advice is therefore
verifiable against the admission code rather than operator folklore, and
it will need revisiting the day a Tier 2 cross-engine broker exists.
