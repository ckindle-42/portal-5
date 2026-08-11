---
id: unit-portal5-bench-execute-v4-failure-playbook
kind: what
title: "PORTAL5_BENCH_EXECUTE_V4 \u2014 Failure playbook"
sources:
- type: code
  path: tests/benchmarks/bench/runners.py
- type: code
  path: scripts/routing_regression.py
- type: code
  path: scripts/execute_preflight.py
last_generated_commit: 9ec2fd4984c047ba49d9056db6a9666a1a4f0caf
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.703467
updated_at: 1784946220.703467
---

- **A model won't load / OOMs** — a very large quantized model plus a long
  context window can exceed unified memory. Skip it and note it; don't force.
- **Persona benches at pool-default TPS not its pin** — served-model
  regression; report it, don't patch it.
- **Pipeline mode much slower than direct for the same model** — expected
  routing overhead, but a large gap on a simple prompt may indicate a
  mis-route; cross-check with `python3 scripts/routing_regression.py
  --assert-baseline`.
- **Preflight retired-alias leak** — surface regression; halt.

## Why

Each failure branch maps to a distinct code surface so the operator knows what
is safe to work around and what is a product bug. OOM is workload-dependent
and skippable; served-model and mis-route issues come from the pipeline
handlers, so `scripts/routing_regression.py --assert-baseline` exists as a
deterministic gate on the resolved `(base, variant, served_model)` tuple. The
retired-alias leak is a hard stop because a non-canonical surface invalidates
every number the run would produce.
