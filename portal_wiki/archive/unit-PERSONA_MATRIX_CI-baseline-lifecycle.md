---
id: unit-PERSONA_MATRIX_CI-baseline-lifecycle
kind: why
title: "PERSONA_MATRIX_CI \u2014 Baseline lifecycle"
sources:
- type: design
  path: docs/PERSONA_MATRIX_CI.md
  section: Baseline lifecycle
last_generated_commit: ''
confidence: high
tags:
- docs
- PERSONA_MATRIX_CI
created_at: 1783195000.882082
updated_at: 1783195000.882082
---


1. **First baseline (per workspace).** Operator runs the matrix locally
   without `--baseline-compare`, inspects results, decides whether the
   numbers represent acceptable behavior, and commits the JSON to:
       `tests/benchmarks/results/persona_matrix_baseline_<workspace>.json`

2. **Re-baselining.** Required after any of:
   - New model added to a backend group on the workspace's chain
   - Existing model upgraded (Ollama re-pull moves the digest)
   - Persona system prompt edited
   - Fixture scenario added/modified
   - Assertion library threshold/regex changed
   Process: run the matrix manually, inspect the diff, commit the new
   baseline if the changes are intentional and acceptable.

3. **Quarterly cadence.** Even with no triggering change, re-baseline
   quarterly to absorb drift in model behavior from re-pulls,
   environmental shifts, or assertion-library tuning.
