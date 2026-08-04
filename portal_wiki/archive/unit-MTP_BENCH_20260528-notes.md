---
id: unit-MTP_BENCH_20260528-notes
kind: why
title: "MTP_BENCH_20260528 \u2014 Notes"
sources:
- type: design
  path: docs/MTP_BENCH_20260528.md
  section: Notes
last_generated_commit: ''
confidence: high
tags:
- docs
- MTP_BENCH_20260528
created_at: 1783195000.879618
updated_at: 1783195000.879618
---


- Baseline via bench_tps.py `--mode pipeline --workspace bench-qwen36-27b --spec-decoding-tag mtp-off --runs 3`
- MTP via direct HTTP to MTPLX server (:18083), `--profile sustained`, 256 max_tokens, temperature 0
- Vendor claim ~2.24× was measured with burst profile; sustained profile trades peak TPS for long-context stability
- 20.1 TPS is interactive but below current auto-coding primary (Laguna-XS.2 at ~40 TPS)
- Quality is lossless at temperature 0 (MTP self-speculative, no external drafter)
- Promotion question: is +9 SWE-bench points (77.2 vs 68.2) worth halving TPS? → coding-shootout-v2 + CC-01 gate
