---
id: unit-portal5-bench-execute-v4-2-bench-plan-the-real-test-count-for-this-run
kind: what
title: "PORTAL5_BENCH_EXECUTE_V4 \u2014 2. Bench plan \u2014 the real test count for\
  \ THIS run"
sources:
- type: code
  path: tests/benchmarks/bench_tps.py
- type: code
  path: tests/benchmarks/bench/cli.py
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.7005088
updated_at: 1784946220.7005088
---

```bash
PORTAL_ENABLE_EVAL=1 python3 tests/benchmarks/bench_tps.py --dry-run
```

`tests/benchmarks/bench_tps.py` is the operator-facing entry shim for the
modularized bench package; it re-exports `main` from `bench/cli.py`. The
`--dry-run` flag prints the configured Ollama model count, the workspace count
from `config/backends.yaml`, the persona count, and the "Total to test" figure
for the current `--mode` without executing any requests. That total is the
authoritative plan for this run.

## Why

The dry-run exists because every count the bench prints comes from live config
rather than a doc: `_config_ollama_models_unique`, `_config_workspaces`, and
`_discover_personas` in `bench/discovery.py` recompute the catalog at startup.
A plan written by hand goes stale the moment a workspace or persona is added.
The `PORTAL_ENABLE_EVAL=1` prefix mirrors the eval module opt-in so the plan
matches what a real run against the pipeline can actually route.
