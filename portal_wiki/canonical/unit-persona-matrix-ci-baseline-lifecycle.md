---
id: unit-persona-matrix-ci-baseline-lifecycle
kind: what
title: "PERSONA_MATRIX_CI \u2014 Baseline lifecycle"
sources:
- type: code
  path: .github/workflows/persona_matrix_nightly.yml
- type: code
  path: portal/modules/eval/persona_matrix/cli.py
- type: code
  path: portal/modules/eval/persona_matrix/sweep.py
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.567778
updated_at: 1784946220.567778
---

The persona matrix treats a committed result file as the reference the CI gate diffs against. The workflow's `Determine sweep parameters` step expects that reference at `tests/benchmarks/results/persona_matrix_baseline_<workspace>.json` and, when present, hands it to the sweep via `--baseline-compare`. A first baseline is therefore an operator action: run the driver locally without `--baseline-compare`, inspect the rendered matrix, and commit the JSON under the workspace-scoped name. The workflow never writes this file — its own sweep output goes to a timestamped `persona_matrix_<workspace>_ci_<ts>.json` artifact — so the baseline can only change through an operator-authored commit.

Re-baselining is warranted when the same inputs that fire the workflow change behavior expectations. The PR path filter watches `config/personas/**` (persona system-prompt edits), `config/backends.yaml` (a model added to a workspace chain), `tests/lib/**` (assertion-library threshold or regex changes), and `tests/fixtures/**` (scenario edits). A model re-pull that moves the Ollama digest is not a file change; it surfaces as a regression in the next baseline diff and is the signal to re-baseline when the new behavior is in spec. The quarterly cadence is operator policy, not code — nothing enforces it; the mechanical backstop is the regression threshold (`--regression-threshold`, default 10pp) applied by `persona_matrix_diff.py`'s `compute_regressions`.

## Why

The lifecycle exists because the CI gate is a diff, not an absolute judge: the workflow can only decide clean or red against a previously committed reference, so an operator must own when that reference moves. Binding the trigger list to the workflow's PR paths makes "when do I re-baseline" mechanically checkable instead of a memory, while digest-drift and quarterly cases stay human judgment, which is why they are policy rather than enforced in code.
