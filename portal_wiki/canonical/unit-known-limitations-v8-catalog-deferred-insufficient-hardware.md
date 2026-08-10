---
id: unit-known-limitations-v8-catalog-deferred-insufficient-hardware
kind: what
title: "KNOWN_LIMITATIONS \u2014 V8 Catalog Deferred (insufficient hardware)"
sources:
- type: code
  path: config/portal.yaml
- type: code
  path: config/backends.yaml
last_generated_commit: 0fec84d46a8898b1b5baf0508af1e25634b099af
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.6766028
updated_at: 1784946220.6766028
---

The following models were evaluated for the V8 catalog and deferred on hardware grounds. None of them is registered in `config/backends.yaml` or appears as a workspace in `config/portal.yaml`, so they are not routable today:

| Model | Est Size | Reason Deferred |
|-------|----------|-----------------|
| `sjakek/Nex-N2-Pro` | ~230GB | 397B total, 17B active — far exceeds 64 GB even at Q1. |
| `DeepSeek-R1-0528` (full) | ~400GB | 671B full model. The 8B distill variant `DeepSeek-R1-0528-Qwen3-8B` is in the catalog instead (the `auto-reasoning` workspace `model_hint`). |
| `Harness-1` (full capability) | n/a | Requires Chroma vector DB + external search state harness. |

`bench-nex-n2-mini` (the smaller N2 line) is present as a bench workspace, so the Nex family is partially covered by the mini variant. Any re-proposal of the deferred entries requires hardware beyond the 64 GB host or a cluster scaling plan.

## Why

Deferral here is a hardware ceiling, not a quality judgment — all three models were considered and excluded because the full-size weights cannot fit the M4 Pro 64 GB budget at any usable quantization. Recording them as deferred (rather than simply absent) tells a future operator they were already evaluated and why, preventing re-litigation, while the note on the N2-mini and R1-0528-8B variants points at what was actually adopted in their place.
