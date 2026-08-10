---
id: unit-known-limitations-p5-mlx-eval-004-large-single-blob-mlx-downloads-hang-intermittently
kind: what
title: "KNOWN_LIMITATIONS \u2014 P5-MLX-EVAL-004 \u2014 Large single-blob MLX downloads\
  \ hang intermittently"
sources:
- type: code
  path: launch.sh
- type: code
  path: scripts/lib/services.sh
- type: code
  path: tests/benchmarks/bench_mlx_hf.py
last_generated_commit: a81c5e73569f981ecedb0d95b088563fcce651ed
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.67051
updated_at: 1784946220.67051
---

- **Description**: During the MLX evaluation, several separate large downloads (each in the 18-26GB range) silently stalled mid-transfer for 30+ minutes with no error — the blob stopped growing with stale TCP close-wait sockets. It happened on both the official registry (`ollama pull`, via `./launch.sh pull-models`) and HuggingFace (`hf download`, the mechanism `scripts/lib/services.sh` uses for ComfyUI pulls), so it is a network/CDN reliability issue for large single-file transfers on this connection, not a tool-specific bug. No stalls appeared on smaller pulls.
- **Mitigation**: A stall-detection wrapper (poll the blob size every 10s, kill and retry after 90s with no growth) recovered every case on retry. It is **not** a committed script — the codebase has no such wrapper today. If large-model pulls become a recurring pain point, promote this pattern into `scripts/`.

## Why

The platform's model-download path is plain `ollama pull` / `hf download` with no progress guard, so an intermittent CDN stall is invisible until the operator notices the transfer stopped. Recording the observed behavior and the throwaway wrapper that fixed it keeps the failure mode known — and documents explicitly that the mitigation is not yet part of the tooling, so nobody assumes the protection exists.
