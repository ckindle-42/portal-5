---
id: unit-known-limitations-v8-catalog-deferred-insufficient-hardware
kind: what
title: "KNOWN_LIMITATIONS \u2014 V8 Catalog Deferred (insufficient hardware)"
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  commit: 05e42ec2
  section: V8 Catalog Deferred (insufficient hardware)
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.6766028
updated_at: 1784946220.6766028
---

| Model | Est Size | Reason Deferred |
|-------|----------|-----------------|
| `sjakek/Nex-N2-Pro` | ~230GB | 397B total, 17B active — far exceeds 64 GB even at Q1. |
| `DeepSeek-R1-0528` (full) | ~400GB | 671B full model. 8B distill variant added (V8 bench-r1-0528-qwen3-8b). |
| `Harness-1` (full capability) | n/a | Requires Chroma vector DB + external search state harness. Standalone model (gpt-oss-20B fine-tune) added to V8 bench-harness1. |

*Last updated: 2026-06-10*
