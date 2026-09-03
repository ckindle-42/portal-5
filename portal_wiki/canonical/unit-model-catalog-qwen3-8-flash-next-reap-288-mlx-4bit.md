---
id: unit-model-catalog-qwen3-8-flash-next-reap-288-mlx-4bit
kind: what
title: "MODEL_CATALOG — `Qwen3.8-Flash-Next-REAP-288-MLX-4bit`"
sources:
- type: code
  path: config/backends.yaml
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1788825600.0
updated_at: 1788825600.0
---

`Qwen3.8-Flash-Next-REAP-288-MLX-4bit` (`sh0wie/Qwen3.8-Flash-Next-REAP-288-MLX-4bit` on Hugging Face) is a REAP expert-pruned MLX affine 4-bit conversion of `Qwen/Qwen3.8-Flash-Next`. REAP (Router-weighted Expert Activation Pruning, arXiv:2510.13999, Lasby et al., ICLR 2026) drops the MoE from 512 to 288 experts; the base is a 180B-class MoE with ~6B active params/token and top-10 routing. The backbone is quantized at group size 64 and the PLE (per-layer-embedding) n-gram table at group size 32. It was added 2026-09-02 (`TASK_OMLX_QWEN38FN_REAP288_BRINGUP_V1`) as a **bench-only** candidate wired to the `bench-qwen38-flash-next-reap288` workspace in `config/portal.yaml` (`module: eval`, `PROMOTE_POLICY=confirm`). `config/backends.yaml` registers it in the `omlx-coding` entry (group `coding`, `priority: 10`) — the same shadow-shift oMLX serving path `auto-coding` uses, but `auto-coding`'s own `model_hint`/priority/aliases are unchanged. There is no GGUF/Ollama fallback for this checkpoint, so the hint is oMLX-only, the same pattern as the `Qwen3.8-27B-4bit` DFlash2 entry.

The checkpoint requires oMLX >= 0.6.4 **and** `qwen4_ple_ssd_offload: true` in `~/.omlx/model_settings.json` (host config, not in this repo). With that setting oMLX keeps the ~32GB PLE n-gram table on SSD and gathers rows through mmap, and its runtime admission size drops from ~77GB full-resident to ~40.6GB; without it oMLX auto-forces the offload only when the memory ceiling is already >= 45GB and otherwise refuses the load with HTTP 507.

Measured on this host 2026-09-02 (the source implementation plan's ~39GB resident / ~68GB full figures were both low): `qwen4_exp_residency_estimate` reports resident 77.2GB, PLE table 32.0GB, checkpoint 73.5GB; oMLX's runtime admission size with the offload setting is ~40.6GB. Even at ~40.6GB the model does not load co-resident with the full Portal Docker stack + Ollama on this 64GB host (~25GB reclaimable in that state), so the Phase 5 load + tool-call probe is deferred to a quiet-host window (Portal stack down / Ollama evicted). Until that probe runs, `supports_tools` is **unprobed and left `false` conservatively — not an audited negative**. Vendor-reported, not reproduced here: 91.5% HumanEval (vs 93.9% stock Q4), ~26-29 tok/s decode on a 48GB M4 Pro.

## Why

Grounding anchors the model to its bench-only oMLX registration and the REAP provenance (512->288 expert pruning of a much larger MoE). Promotion to `auto-coding`'s production default is an explicit `[GATE]` in the bring-up task, decided only after this workspace has head-to-head evidence against the Laguna-XS.2 primary. The corrected memory numbers and the hard `qwen4_ple_ssd_offload` requirement are what a future session needs before attempting a bench; the tool-call capability is left unverified rather than guessed because the load probe never succeeded.
