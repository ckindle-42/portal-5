---
id: unit-known-limitations-p5-mlx-eval-004-large-single-blob-mlx-downloads-hang-intermittently
kind: what
title: "KNOWN_LIMITATIONS \u2014 P5-MLX-EVAL-004 \u2014 Large single-blob MLX downloads\
  \ hang intermittently"
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  commit: 05e42ec2
  section: "P5-MLX-EVAL-004 \u2014 Large single-blob MLX downloads hang intermittently"
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.67051
updated_at: 1784946220.67051
---

- **Description**: During evaluation, 3 separate large (18-26GB) downloads
  (both `ollama pull` from the official registry and `huggingface_hub`
  pulls from HF) silently stalled mid-transfer for 30+ minutes with no error
  — the blob simply stopped growing, with stale TCP `CloseWait` sockets.
  Happened on both registries, so it isn't tool-specific; likely a
  network/CDN reliability issue for large single-file transfers on this
  connection. No stalls on smaller pulls.
- **Mitigation**: A stall-detection wrapper (poll blob size every 10s, kill
  + retry after 90s with no growth) recovered every case on retry. Not
  currently a committed script — if large-model pulls become a recurring
  pain point, consider promoting this pattern into `scripts/`.
