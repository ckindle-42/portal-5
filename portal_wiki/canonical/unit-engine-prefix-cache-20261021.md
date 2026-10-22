---
id: unit-engine-prefix-cache-20261021
kind: what
title: Engine prefix-cache measurements on this host (2026-10-21)
sources:
- type: code
  path: portal/platform/inference/ollama_native.py
claims: []
confidence: high
tags:
- engine
- omlx
- ollama
- measurement
created_at: 1792540800
updated_at: 1792680000
---

Measured 2026-10-21 on the M4 Pro with 64 GB unified memory. The figures below are that day's timings and disk sizes, not a live inventory.

A growing prefix was reused on four serving paths while the process stayed up. Ollama 0.40.5 reused it for a Qwen3.6 hybrid by llama.cpp context checkpoints. oMLX 0.7.2 reused it from its block cache. The Pipeline, which passes an oMLX body through `_omlx_request` and translates an Ollama body in `to_native_request`, reused it as well. Ollama 0.40.8's MLX runner reused it for Flint. As of 2026-10-22 that 0.40.8 build is the live managed Ollama (`~/ollama-live/VERSION`), installed by the updater with a passing contract, and the library tag `flint:40b-a2b-qat-int4` is present. The timings in this unit stay that day's measurements. The exception is an Ollama sidecar whose server keep-alive is zero: the runner is torn down after each call, and the next call has no cache to resume. The pipeline still does not forward `keep_alive` (`to_native_request`); that separate choice is [[unit-known-limitations-ollama-v1-sampling-drop]].

On oMLX the usage field `cached_tokens` is the size of the blocks written at the end of the request. opencode's cache.read is that stored size, copied forward, so it does not say how many tokens the following call actually resumed. One Qwen3.8-27B seat on oMLX still took from about 8 s to about 245 s to first token at similar prompt lengths while the field looked warm. The constraint this creates for anyone reading a trace is [[unit-known-limitations-omlx-prefix-cache-accounting]].

The on-disk copy lives at the default directory ~/.omlx/cache (setting cache.ssd_cache_dir). A max size of auto takes half of whatever disk is free. That directory had reached 189 GB. Upgrading to oMLX 0.7.2 then left 166 GB of blocks from 0.7.0 marked skipped_incompatible. The cap on this machine is now 64 GB. Per 4096-token block the same measurement is about 38 MB at the median and 231 MB at p90, so one 64K-token agent session is about 3–8 GB. A working set of 15–25 GB is what that 64 GB cap is meant to hold, on the order of 8–12 sessions. Admitting a second oMLX model evicts the one that is resident and deep-resets the caches, so a prefix just stored does not survive the next oMLX load.

Decode on Ollama GGUF the same day was about 7–10 tok/s for a dense 27B seat and about 29–30 tok/s for the 35B-A3B mixture-of-experts seats. opencode invoked as run with format json emits no reasoning events, so thinking time appears as a quiet gap between events rather than as tokens.

## Why

Seat traces were being scored as if a large cache.read meant the prefix had been reused, and quiet stretches were being scored as a stalled engine. The day's runs separate those. Reuse is real on the four paths when the runner stays resident, the oMLX usage field does not prove it, a zero keep-alive sidecar throws the cache away, and a dense 27B GGUF decode is several times slower than the mixture-of-experts seats on this host. The disk figures are here so the next oMLX upgrade is not surprised by a directory that filled half the free volume with blocks the new build will not load.
