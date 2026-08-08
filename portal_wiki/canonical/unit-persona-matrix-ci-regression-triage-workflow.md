---
id: unit-persona-matrix-ci-regression-triage-workflow
kind: what
title: "PERSONA_MATRIX_CI \u2014 Regression triage workflow"
sources:
- type: code
  path: tests/persona_matrix_diff.py
- type: code
  path: portal/modules/eval/persona_matrix/cli.py
- type: code
  path: portal/modules/eval/persona_matrix/sweep.py
- type: code
  path: portal/modules/eval/persona_matrix/_common.py
- type: code
  path: .github/workflows/persona_matrix_nightly.yml
last_generated_commit: 9623f6b25b3e922bd0cf4b3885a926a4728b26a1
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.569202
updated_at: 1784946220.569202
---

When a CI sweep surfaces a regression, the diff names the exact cell: `persona_matrix_diff.py` indexes cells by `(persona, backend, model)` and prints regressions as `persona on backend/model` with the PASS-rate delta in percentage points. To reproduce the cell in isolation, run the driver locally with the substring filters the CLI supports — `--workspace`, `--persona`, `--model`, `--output` (an output path such as one under `/tmp`) — so the sweep executes only that one cell. The JSON report's per-scenario entries carry the assertion `name`, `passed`, `severity`, and `detail` (built by `run_cell` in `sweep.py`), so you can see which assertion flipped from PASS to FAIL.

The three common causes map to real mechanisms. Model digest drift follows an `ollama pull` that changed model behavior; it surfaces as a regression in the next baseline diff, and re-baselining is the remedy when the new behavior is in spec. A persona system-prompt edit is tracked by the workflow's `config/personas/**` PR path; the fix is either revising the prompt or relaxing the assertion in `tests/lib/`. A genuine regression means the model got worse, and the demotion target is the workspace's `threshold_doc` from `WORKSPACE_REGISTRY` — `docs/COMPLIANCE_FALLBACK_POLICY.md` for `auto-compliance`.

## Why

Triage is the operator-facing complement to the mechanical diff: the diff can only say a cell dropped, never why, so the workflow exists to narrow a whole-matrix failure down to one assertion on one model. Grounding each cause to a concrete mechanism — the diff's cell key, the CLI substring filters, the JSON assertion payload, and the registry's `threshold_doc` — keeps the triage steps runnable against HEAD instead of relying on the doc's prose.
