---
id: unit-HOWTO-media-memory-and-launch-order
kind: why
title: Media memory and launch order
sources:
- type: code
  path: portal/modules/media/tools/_admission.py
- type: code
  path: config/portal.yaml
claims: []
confidence: high
tags:
- HOWTO
- media
- memory
- verified-v1
created_at: 1784057635.351039
updated_at: 1784057635.351039
---

# Media memory and launch order

The MLX media generators (MFLUX image :8933, video-mlx :8935, MiniMax music
:8912) and Ollama share the same 64GB unified-memory pool on Apple Silicon,
with **no cross-engine backpressure**: Ollama's `OLLAMA_MAX_LOADED_MODELS` /
`OLLAMA_MEMORY_LIMIT` do not govern the MLX generators, and the retired
MLX-proxy admission gate (`3a0c58e`) never covered media backends either. See
`unit-fact-media-memory-budget` for per-backend GB estimates.

## The guard

Each media generation job passes a `mflux:*` / `video_mlx:*` / `music:*` key
through the Tier-1 pre-flight admission check
(`portal/modules/media/tools/_admission.py`, `admit()`) before it starts. The
check compares the model's measured peak plus a headroom margin against a
live free-memory snapshot (`vm_stat` on macOS) and returns a structured,
retryable refusal rather than letting the job OOM the box. It fails open when
free memory can't be measured.

## Safe co-residency matrix

| Active combination | Safe? | Why |
|---|---|---|
| Ollama small/medium model (<20GB) + MFLUX schnell/klein (~15–18GB) | Usually | Admission still checks current free memory plus headroom |
| Ollama large model (30GB+) + MFLUX qwen-image (~22GB) | Marginal or refused | Unload the Ollama model first (`ollama stop <model>`) |
| Any Ollama model + video-mlx (LTX-2.3, ~24–34GB) | Marginal | Video is thermally heavy and off by default; run it with the box otherwise quiet |

## Launch order (until a Tier 2 cross-engine broker exists)

1. Before a large media job, check what's loaded: `curl localhost:11434/api/ps`
   (Ollama) and the target backend's estimated GB (`unit-fact-media-memory-budget`).
2. If a large Ollama model is loaded and the media job is also large, unload the
   Ollama model first (`ollama stop <model>`) or wait for `KEEP_ALIVE` to expire.
3. The MLX generation servers release memory between jobs — if a job is refused,
   wait a few minutes and retry rather than restarting the service.
4. The Tier-1 check cannot see what Ollama or another in-flight job will use
   beyond the free-memory snapshot at admission time, so steps 1–2 still matter.

## Why

This guidance exists because the MLX media generators and Ollama share one
unified-memory pool with no cross-engine broker, so a large media job can OOM a
system that looks idle to either stack alone. The co-residency matrix and
launch-order steps are grounded in the per-backend peak estimates in
`portal/modules/media/tools/_admission.py` (mirrored from
`unit-fact-media-memory-budget`) and the remediation strings that check returns
in its structured refusal — verifiable against the admission code rather than
operator folklore, and due for revisiting the day a Tier 2 broker exists.
