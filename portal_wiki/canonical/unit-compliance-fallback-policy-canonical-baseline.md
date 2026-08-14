---
id: unit-compliance-fallback-policy-canonical-baseline
kind: what
title: "COMPLIANCE_FALLBACK_POLICY \u2014 Canonical baseline"
sources:
- type: code
  path: portal/modules/eval/persona_matrix/cli.py
- type: code
  path: portal/modules/eval/persona_matrix/_common.py
- type: code
  path: portal/modules/eval/persona_matrix/loaders.py
- type: code
  path: tests/lib/compliance_assertions.py
- type: code
  path: tests/fixtures/compliance_scenarios.yaml
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.564456
updated_at: 1784946220.564456
---

The accepted baseline for the compliance matrix is stored at `tests/benchmarks/results/persona_matrix_baseline_auto-compliance.json`, a `portal5.persona_matrix.v1` report produced by `tests/portal5_persona_matrix.py`. Without an explicit `--output`, the driver writes to `RESULTS_DIR` using the workspace-scoped name `persona_matrix_<workspace>_<utc-stamp>.json`; the baseline file keeps the same shape so `persona_matrix_diff` and `--baseline-compare` can diff against it. Re-baselining is warranted whenever any sweep input changes: a model added or upgraded in the `ollama-reasoning` or `ollama-general` groups (`config/backends.yaml`), a compliance persona system prompt edit (`config/personas/*.yaml`), a fixture scenario change (`tests/fixtures/compliance_scenarios.yaml`), or an assertion library change (`tests/lib/compliance_assertions.py`). The quarterly cadence is operator policy and is not enforced by any code.

## Why

The baseline is a machine artifact, not a document: it is the output of the same driver the regression diff consumes, so its location and schema must match what `persona_matrix_diff` reads. Naming it with the workspace id keeps one chain's baseline from colliding with another in the shared results directory, and the trigger list simply names the inputs the sweep loads, so a stale baseline is attributable to a specific change rather than to unknown drift.
