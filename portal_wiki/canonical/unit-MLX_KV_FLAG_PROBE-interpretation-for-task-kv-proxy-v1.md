---
id: unit-MLX_KV_FLAG_PROBE-interpretation-for-task-kv-proxy-v1
kind: why
title: "MLX_KV_FLAG_PROBE \u2014 Interpretation for TASK_KV_PROXY_V1"
sources:
- type: design
  path: docs/MLX_KV_FLAG_PROBE.md
  section: Interpretation for TASK_KV_PROXY_V1
last_generated_commit: ''
confidence: high
tags:
- docs
- MLX_KV_FLAG_PROBE
created_at: 1783195000.878207
updated_at: 1783195000.878207
---


**mlx_lm.server (text path)**: ALL KV flags are ABSENT as of 0.31.3. This includes
`--kv-cache-quantization`, which means the existing legacy int8 fallback in the proxy
(line ~878) is already a dead code path and will not inject. Wire `MLX_LM_KV_BITS` and
`max_kv_size` support as forward-compatible infrastructure: when a future mlx_lm adds
these flags, the proxy will activate them without code changes.

**mlx_vlm.server (vision path)**: Full KV support present. `--kv-bits`, `--kv-quant-scheme`,
`--kv-group-size`, and `--max-kv-size` are all supported. The existing `MLX_VLM_KV_BITS`
env var is the proven path; per-model `kv_bits` and `max_kv_size` in backends.yaml
override it at finer granularity.

**Conditional wiring rules for TASK_KV_PROXY_V1**:
- `MLX_LM_KV_BITS` env var: wire unconditionally (infrastructure), flag injection gated by probe
- `MLX_LM_KV_QUANT_SCHEME` env var: wire unconditionally (infrastructure)
- `max_kv_size` on mlx_lm models: YAML annotation + resolver built, but `--max-kv-size` not passed (flag absent)
- `max_kv_size` on mlx_vlm models: fully enforced via `--max-kv-size` flag
- `--kv-cache-quantization int8` legacy check: remove or gate it behind probe result (flag now absent)

**Note on `--draft-kind`**: ABSENT on mlx_lm, PRESENT on mlx_vlm (dflash, mtp). P5-MTP-001
(MTP speculative decoding) is unblocked for the VLM path. Out of scope for this task series.
