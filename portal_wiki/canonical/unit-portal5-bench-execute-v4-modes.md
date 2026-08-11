---
id: unit-portal5-bench-execute-v4-modes
kind: what
title: "PORTAL5_BENCH_EXECUTE_V4 \u2014 Modes"
sources:
- type: code
  path: tests/benchmarks/bench/cli.py
- type: code
  path: tests/benchmarks/bench/runners.py
- type: code
  path: tests/benchmarks/bench/measure.py
last_generated_commit: 3771ef49a112fde1d667c67af5bf1bc003ce75b4
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.702423
updated_at: 1784946220.702423
---

`bench_tps.py` selects test tiers with `--mode` (choices in
`tests/benchmarks/bench/cli.py`: `direct`, `pipeline`, `personas`, `all`,
default `all`):
- **direct** — each Ollama model hit directly on Ollama (raw model TPS).
- **pipeline** — each workspace through the pipeline at `:9099` (routing +
  serving overhead).
- **personas** — each persona's `workspace_model` through the pipeline; the
  result is tagged with `persona_slug` but the request model is the
  workspace, so `model_pin` is not exercised by this mode.

## Why

The three tiers isolate different overheads: direct isolates raw model speed,
pipeline adds routing, and personas exercises the persona-to-workspace
mapping (`_resolve_persona_workspace` in `portal/platform/inference/router/
preinject.py`). `bench_personas` sends the persona's `workspace_model`, not
the persona slug, so a `model_pin` persona benches its workspace's pool
default — pin-serving correctness is verified separately by
`scripts/persona_intent_audit.py` and `routing_regression.py`, not by this
mode's TPS.
