---
id: unit-module-eval
kind: mixed
title: "Eval Module \u2014 cross-cutting bench apparatus (off by default)"
sources:
- type: code
  path: portal/modules/eval/persona_matrix/sweep.py
- type: code
  path: portal/platform/wiki/adapters/modules.py
- type: code
  path: config/portal.yaml
claims:
- probe: modules.disabled
  contains: eval
confidence: high
tags:
- eval
- module
- verified-v1
created_at: 1783822263.5599139
updated_at: 1783822263.5599139
---

# Eval Module — cross-cutting bench apparatus (off by default)

Per DESIGN-MODULES-V1: bench/testing apparatus is not a use-module,
disabled by default. Each discipline keeps its OWN eval/ (e.g.
portal.modules.security.eval) — this is the SHARED cross-cutting layer
used across disciplines, not owned by any one of them.

## Contents

portal.modules.eval.persona_matrix — persona coverage matrix sweep
(sweep.py, cli.py, loaders.py, ollama_client.py, render.py). Entry
point: tests/portal5_persona_matrix.py. Diff tool (tests/persona_matrix_diff.py)
and nightly CI (.github/workflows/persona_matrix_nightly.yml) stay at
their existing tests/ locations — they are thin, standalone, and have
no code dependency on the moved package.

## Scope note

The broader tests/benchmarks/ top-level bench_*.py harnesses (bench_tps,
bench_capability, bench_router, etc.) were NOT moved in this pass —
several have real interdependencies (e.g. bench_lab_exec.py is a live
dependency of security core/_data.py) that need individual verification,
not a batch move. persona_matrix was the cleanly self-contained,
explicitly-named cross-cutting harness in the spec.

## Module State

The switch is `modules.eval.enabled` in `config/portal.yaml` (`portal module enable|disable` writes it). This unit documents the switch; it does not hold it.

## Why

Eval ships disabled. `portal/platform/wiki/adapters/modules.py` treats a
missing `modules.eval` key, or `enabled: false`, as off
(`DEFAULT_DISABLED_MODULES`). Bench workspaces stay unrouted until an
operator sets `modules.eval.enabled` or `PORTAL_ENABLE_EVAL` (the
adapter's `_eval_env_opt_in`). The unit is sourced to the adapter, the
persona-matrix package it gates, and `config/portal.yaml`.
