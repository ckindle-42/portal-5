---
id: unit-known-limitations-ling-3-0-flash-turboquant-memory-gates
kind: what
title: "KNOWN_LIMITATIONS \u2014 Ling-3.0-flash TurboQuant build + memory gates"
sources:
- type: code
  path: config/portal.yaml
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1786393800.0
updated_at: 1786393800.0
---

- **ID**: P5-LING30-GATE-C
- **Status**: Deferred; not benched. TASK-BATCH-BENCH-002 Part C finding.
- **Description**: `AtomicChat/Ling-3.0-flash-GGUF` (`bailingmoe3` MoE, 124B/5.1B-active, hand-placed Atomic Dynamic quants) was gated behind two checks before any bench attempt, both of which failed on this box (2026-08-10):
  - **GATE-C1 (memory headroom)**: the smallest viable rung is ~`AD-IQ2_M` at 49GB. This 64GB box's realistic single-model ceiling, even after the `OLLAMA_GPU_OVERHEAD` fix (see `P5-OLLAMA-GPU-OVERHEAD-001`), leaves only ~36-44GB — a 49GB load would need the entire MCP fleet + Docker VM evicted, an operator call this task correctly declined to make unilaterally.
  - **GATE-C2 (custom build)**: these GGUFs require AtomicChat's TurboQuant llama.cpp build (`bailingmoe3` upstream + their bugfixes), not stock Ollama. Only stock `llama-server` (`/opt/homebrew/bin/llama-server`) is present; no TurboQuant build is staged, and building one is explicitly out of scope for this task.
- **Value if unblocked**: the Atomic Dynamic quant-methodology datapoint (hand-placed bits, card claims 31-41% closer to BF16 than stock quants) is the actual interest here, more than a fleet slot — a future attempt should capture a KL/quality read, not just t/s.

## Why

Recording both gate failures with their specific numbers (49GB rung, no TurboQuant build present) means a future session doesn't have to re-derive whether this candidate is worth attempting — it can check whether either constraint has changed (more RAM, a TurboQuant build becomes available) before re-evaluating, rather than re-running the same failed preflight.
