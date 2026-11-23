---
id: unit-code-tests
kind: what
title: tests subsystem (656 files)
sources:
- type: code
  path: tests/__init__.py
  commit: 2d5a330838e1
- type: code
  path: tests/_netguard/netguard.py
  commit: 2d5a330838e1
- type: code
  path: tests/_netguard/sitecustomize.py
  commit: 2d5a330838e1
- type: code
  path: tests/benchmarks/bench/__init__.py
  commit: 2d5a330838e1
- type: code
  path: tests/benchmarks/bench/adhoc_probe.py
  commit: 2d5a330838e1
claims:
- probe: repo.path.exists
  path: tests/__init__.py
  equals: true
confidence: high
tags:
- code
- tests
---

# tests subsystem

**Files:** 656

- `tests/__init__.py`
- `tests/_netguard/netguard.py`
- `tests/_netguard/sitecustomize.py`
- `tests/benchmarks/bench/__init__.py`
- `tests/benchmarks/bench/adhoc_probe.py`
- `tests/benchmarks/bench/cli.py`
- `tests/benchmarks/bench/config.py`
- `tests/benchmarks/bench/discovery.py`
- `tests/benchmarks/bench/lifecycle.py`
- `tests/benchmarks/bench/measure.py`
- `tests/benchmarks/bench/notify.py`
- `tests/benchmarks/bench/prompts.py`
- `tests/benchmarks/bench/report.py`
- `tests/benchmarks/bench/results_io.py`
- `tests/benchmarks/bench/runners.py`
- `tests/benchmarks/bench_cad_gauntlet_v2.py`
- `tests/benchmarks/bench_cad_probe.py`
- `tests/benchmarks/bench_candidates_v10.py`
- `tests/benchmarks/bench_capability.py`
- `tests/benchmarks/bench_compliance_probe.py`
- ... and 636 more
