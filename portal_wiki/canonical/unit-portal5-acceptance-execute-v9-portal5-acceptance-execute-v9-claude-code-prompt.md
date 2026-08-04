---
id: unit-portal5-acceptance-execute-v9-portal5-acceptance-execute-v9-claude-code-prompt
kind: what
title: "PORTAL5_ACCEPTANCE_EXECUTE_V9 \u2014 PORTAL5_ACCEPTANCE_EXECUTE_V9 \u2014\
  \ Claude Code Prompt"
sources:
- type: code
  path: tests/portal5_acceptance_v6.py
- type: code
  path: tests/acceptance/s03_routing.py
- type: code
  path: tests/acceptance/s06_security_workspaces.py
- type: code
  path: scripts/execute_preflight.py
- type: code
  path: tests/acceptance/runner.py
- type: code
  path: tests/expected_models.py
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.6935182
updated_at: 1784946220.6935182
---

The current acceptance entry point is `tests/portal5_acceptance_v6.py`, a thin
script that re-exports the routing signal dicts and delegates to
`acceptance.cli.main`; confirm it is still the newest runner by listing the
`portal5_acceptance_*` shims under `tests/` before running.

Two changes mark the current surface. First, the retired standalone security
workspace ids no longer exist as workspace ids: S6 tests the `auto-security`
workspace with variant awareness, and `scripts/execute_preflight.py` maintains
the `RETIRED_ALIASES` guard list that fails the run if such an id reappears.
Second, routing integrity is now assertable: `scripts/routing_regression.py
--assert-baseline` checks the served-model tuple against
`tests/routing/baseline.json`, and the `model_pin` persona field is enumerated
by the preflight so S10 can verify the served model. S3 and S21 perform
expected-model matching per request through `tests/expected_models.py`.

Bench workspaces are out of acceptance scope by design: `s03_routing.py`
excludes `bench-*` ids, the runner registers no bench sections in
`ALL_SECTIONS`, and full-catalog routing plus TPS measurement belongs to
`tests/benchmarks/bench_tps.py`. The acceptance suite is not a benchmark and
asserts no TPS or performance figures. Scale is config-driven — run the
preflight and read the live numbers rather than trusting a figure written into
a document.

## Why

This unit exists to stop an operator from running the acceptance suite against
stale assumptions: the old execution doc baked a workspace count and referenced
retired security ids, both already wrong at the codebase state the doc
described. The corrected surface derives everything from the preflight and the
section code, so the suite's target is whatever `config/portal.yaml` says today,
and the retired-id guard turns a regression back into an immediate failure.
