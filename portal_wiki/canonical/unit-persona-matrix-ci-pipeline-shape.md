---
id: unit-persona-matrix-ci-pipeline-shape
kind: what
title: "PERSONA_MATRIX_CI \u2014 Pipeline shape"
sources:
- type: code
  path: .github/workflows/persona_matrix_nightly.yml
- type: code
  path: tests/portal5_persona_matrix.py
- type: code
  path: portal/modules/eval/persona_matrix/cli.py
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.567413
updated_at: 1784946220.567413
---

The persona-matrix workflow has no scheduled cron trigger. `persona_matrix_nightly.yml` declares only workflow_dispatch (manual) and pull_request (path-scoped), and the file's own header comment explains why: no self-hosted runner is kept online for this repo, so a cron would queue forever and be auto-cancelled by GitHub. The PR path filter narrows runs to changes that plausibly alter matrix outcomes: `config/personas/**`, `config/backends.yaml`, `tests/lib/**`, `tests/fixtures/**`, and `tests/portal5_persona_matrix.py`.

```
[workflow_dispatch (workspace + backend inputs)] ──┐
[PR touching personas / backends / lib / fixtures] ┤── persona-matrix-nightly (self-hosted)
                                                   ┘          │
                                                              ▼
                                                     pre-flight: pipeline :9099 + Ollama :11434 health
                                                              │
                                                              ▼
                                                     tests/portal5_persona_matrix.py --baseline-compare --regression-threshold 10
                                                              │
                                                              ▼
                                                     tests/benchmarks/results/persona_matrix_<ws>_ci_<ts>.json   (uploaded artifact)
                                                              │
                                                              ▼
                                                     tests/persona_matrix_diff.py vs baseline   (run log, no PR comment)
                                                              │
                                                              ▼
                                                     exit 0 clean / 1 FAIL-or-regression / 2 both   (job status)
```

The `tests/portal5_persona_matrix.py` entrypoint is a thin shim that delegates to `portal.modules.eval.persona_matrix` (`cli.main`), so the sweep, loaders, and diff integration live in the module tree rather than in `tests/`.

## Why

The shape matters because the doc that produced this unit drew a `[scheduled cron]` input that the workflow explicitly forbids — a cron on this repo was empirically shown to queue forever across months of scheduled runs before it was removed. Restating the shape from the actual trigger and step structure makes the unit describe the real CI topology, and keeping the diagram fenced preserves it as a stable reference that does not drift the way prose would.
