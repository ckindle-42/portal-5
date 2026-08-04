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
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
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

```yaml
enabled: false
```

## Why

The eval module is the one module disabled by default, and that default is
load-bearing: `portal/platform/wiki/adapters/modules.py` treats a missing
or `false` `enabled:` field as off (per `DEFAULT_DISABLED_MODULES`), and
the bench workspaces it owns stay unrouted until an operator flips the
toggle or sets `PORTAL_ENABLE_EVAL` (mirrored by the adapter's
`_eval_env_opt_in`). Because bench apparatus is cross-cutting rather than
owned by one discipline, its activation is an explicit, confirm-gated
decision — the state change is recorded as a `module-state-change:`
provenance source by `writeback_module.py`. The unit is sourced to the
adapter that reads the toggle, the persona-matrix package it gates, and
`config/portal.yaml` where the bench workspaces are declared.
