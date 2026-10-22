---
id: unit-known-limitations-omlx-prefix-cache-accounting
kind: what
title: oMLX prefix cache reports stores, resets on admission, and the SSD default is unbounded
sources:
- type: code
  path: portal/platform/inference/ollama_native.py
claims: []
confidence: high
tags:
- known-limitations
- omlx
- cache
created_at: 1792540800
updated_at: 1792540800
---

## oMLX prefix cache — a store is not a hit, another model wipes it, and auto fills the disk (2026-10-21)

- **ID**: P5-OMLX-PREFIX-CACHE-001
- **Status**: OPEN. Host measurement 2026-10-21, oMLX 0.7.2, M4 Pro, 64 GB. The pipeline does not rewrite the figure: `_omlx_request` sends the chat body on unchanged, so clients see the engine's usage object. Numbers and the paths where reuse did hold are in [[unit-engine-prefix-cache-20261021]].
- **Not a hit counter**: after a call, oMLX puts the length of the blocks it just saved into usage `cached_tokens`. opencode's cache.read is that saved length from the previous call. Reading either one as "tokens resumed" is wrong. First-token latency on a warm-looking seat still moved by more than an order of magnitude.
- **Residency**: only one oMLX model stays loaded. Bringing another in unloads the current one and deep-resets every cache, including a prefix saved moments earlier. There is no error on the request that lost it.
- **Disk**: the SSD directory defaults to ~/.omlx/cache. Leaving the max size on auto means half of free space, which on this volume grew to 189 GB. The 0.7.2 process then refused 166 GB of those blocks as incompatible with 0.7.0. The directory is capped at 64 GB. Budget roughly 38 MB typical and 231 MB at the 90th percentile for each 4096-token block, about 3–8 GB for a 64K-token agent session, and a 15–25 GB working set — the cap then covers something like 8–12 sessions.
- **Mitigation**: cap the directory, and judge reuse from first-token time or an engine log that names a resumed block, not from cache.read. Do not admit a second oMLX model during a seat that must keep its prefix.

## Why

The field is named as if it were a hit, and the client copies it into a read counter, so a trace looks warm while oMLX is still pre-filling. That sends the next look at the pipeline, which only forwarded the number. A second model load and an uncapped directory are the other two silent ways a seat goes cold: admission clears process caches, and blocks kept from the previous oMLX build are skipped after an upgrade instead of being resumed. The cap and the per-block size are what make 64 GB a chosen working set rather than another fill-the-disk default.
