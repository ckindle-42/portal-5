---
id: unit-persona-matrix-ci-ci-vs-local-run-boundary
kind: what
title: "PERSONA_MATRIX_CI \u2014 CI vs. local-run boundary"
sources:
- type: code
  path: .github/workflows/persona_matrix_nightly.yml
- type: code
  path: tests/persona_matrix_diff.py
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.5681589
updated_at: 1784946220.5681589
---

CI runs on a self-hosted runner because the sweep and its pre-flight step need host access to the Portal 5 stack. The workflow's `runs-on: self-hosted` line and its Pre-flight step curl `localhost:9099` (pipeline health) and `localhost:11434` (Ollama version) before the sweep starts; a public GitHub-hosted runner has neither of those loopback services. If the self-hosted runner is offline the job queues — the workflow declares no fallback label, so GitHub has no hosted pool to spill onto.

The CI run is non-destructive by construction. Sweep output lands at `tests/benchmarks/results/persona_matrix_<workspace>_ci_<ts>.json`, is uploaded as a `persona_matrix-*` artifact with `retention-days: 30`, and is never committed by the workflow. The baseline file is only read (passed to `--baseline-compare`), so baseline updates require an operator-authored commit. The workflow does not post a PR comment: it prints the `persona_matrix_diff.py` summary to the run log and, when the sweep exited non-zero, fails the job with that same exit code — a failed PR check blocks merge, while a manual dispatch failure only marks that run red.

## Why

The boundary is a consequence of the local-first architecture: the matrix measures real local models, so the runner must be the machine that can reach them, and the results must not mutate the repo. Splitting measure from change keeps CI safe to run unattended — the workflow can fail loudly and upload evidence, but it can never overwrite a baseline or leak a result into version control, which is what allows the nightly gate to run with zero operator supervision.
