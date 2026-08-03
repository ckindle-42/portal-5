---
id: unit-bench-tps
kind: mixed
title: "Bench TPS entry \u2014 operator-facing re-export shim"
sources:
- type: code
  path: tests/benchmarks/bench_tps.py
  commit: f09fdb85
last_generated_commit: f09fdb85
claims: []
confidence: high
tags:
- authored-v1
- tests
- bench
created_at: 1785798617.443697
updated_at: 1785798617.443697
---

`bench_tps.py` is the stable operator-facing entry point for the TPS bench:
the implementation lives in the `tests/benchmarks/bench` package, and this
file re-exports all public names so existing importers and invocations keep
working.

## Why

The modularization moved the implementation into the bench package, and a
restructure that breaks `python3 tests/benchmarks/bench_tps.py` or
`from tests.benchmarks import bench_tps` would break every workflow and
prompt that invokes the bench. The file is the compatibility contract: the
same invocation works exactly as before, and every public name is re-exported
from the module that now owns it. The docstring's monkeypatching note is the
operational guidance — a test that patches internals must target the owning
module, not the re-export.

## Interfaces

Re-exports `main`, `bench_tps`, the runners, the config constants, and the
discovery/lifecycle/measure helpers from the bench package.

## Gotchas

The unconditional `sys.path.insert(0, ...)` to the repo root exists because
an editable install of an unrelated `portal` package elsewhere on the machine
can shadow this repo's — the insert always wins, even when the path is
already present but mispositioned.
