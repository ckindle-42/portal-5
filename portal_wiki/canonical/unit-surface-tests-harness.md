---
id: unit-surface-tests-harness
kind: mixed
title: Test-tree scaffolding and shared harness library
sources:
- type: code
  path: tests/*.py
- type: code
  path: tests/lib/*.py
last_generated_commit: c742f52182d730944300a2bd86560665c8371e8a
claims: []
confidence: high
tags:
- authored-v1
- tests
created_at: 1785883400.0
updated_at: 1785883400.0
---

The test tree's scaffolding and shared harness library is the substrate every driver
builds on: entry shims that forward to packages, a pure-Python helper contract under
`tests/lib`, and standalone scoring and reporting modules.

## Why

The suite is one shared contract, not a scatter of per-file mirrors. Centralising
assertion severities, scenario fixtures, and the result model stops harnesses from
scoring a scenario differently, and the hermetic rule — pure stdlib, no Docker, no
network — keeps it unit-testable on a bare clone. Shims preserve historical commands;
new features live in the packages they delegate to.

## Interfaces

`conftest.py` seeds `PIPELINE_API_KEY` and `LAB_*` defaults before pipeline imports;
`common.py` exports `REFUSAL_PHRASES`. `expected_models.py` derives routing ground
truth via `expected_model_keys`, `model_matches_expected`, and `resolve_expected`.
`tests/lib` supplies `AssertionResult`/`ScenarioOutcome`, `expand_scenarios`,
`run_assertions`, the result model, and the `stream_wait` idle-gap waiter.
`quality_score`, `score_function_recall`, `classify_lines`, `compute_regressions`,
`added_removed_cells`, and `build_dashboard` cover scoring and reporting. The shims
`portal5_acceptance_v6.py`, `portal5_acceptance_comfyui.py`, `portal5_uat_driver.py`,
and `portal5_persona_matrix.py` forward to their packages.

## Gotchas

Fixture loaders are transforms over scenario YAML, never the source of truth; an
unknown assertion name must fail loudly. Quality signals and the refusal keyword
check stay coupled to what they were tuned against. And the wall-clock ceiling in
`stream_wait` is a backstop — using it as the primary driver reintroduces the
flakiness the idle-gap detection removes.
