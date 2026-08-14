---
id: unit-compliance-fallback-policy-re-running-the-matrix
kind: what
title: "COMPLIANCE_FALLBACK_POLICY \u2014 Re-running the matrix"
sources:
- type: code
  path: portal/modules/eval/persona_matrix/cli.py
- type: code
  path: portal/modules/eval/persona_matrix/sweep.py
- type: code
  path: tests/persona_matrix_diff.py
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.565172
updated_at: 1784946220.565172
---

Re-running the compliance matrix means invoking the persona-matrix driver against `auto-compliance` with the same inputs that produced the stored baseline. The driver is `tests/portal5_persona_matrix.py`, a compat shim for `portal.modules.eval.persona_matrix`. The flags in `cli.py` shape the run: `--workspace` (default `auto-compliance`), `--persona` and `--model` (substring filters on slugs and model ids), `--backend ollama` (backend-type filter), `--require` (hard model-presence gate that exits 3), `--dry-run` (print the plan without calling Ollama), `--include-big-models` (admit models otherwise skipped), and `--baseline-compare` with `--regression-threshold` (inline regression diff against a stored baseline). A re-run should reuse the same flags as the original sweep, because the regression diff only compares cells with matching persona, backend and model keys and silently ignores cells absent from either report.

## Why

Re-running a benchmark correctly is the same discipline as running it the first time: every filter changes which cells the report contains, and the diff tool ignores cells missing from either side, so a mismatched flag set produces a comparison that is quietly incomplete. Naming the flags that shape the chain turns "re-run the matrix" from a remembered command into a reproducible contract the operator can verify cell by cell.
