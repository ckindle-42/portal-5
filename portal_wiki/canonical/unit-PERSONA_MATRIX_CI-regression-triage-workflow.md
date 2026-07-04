---
id: unit-PERSONA_MATRIX_CI-regression-triage-workflow
kind: why
title: "PERSONA_MATRIX_CI \u2014 Regression triage workflow"
sources:
- type: design
  path: docs/PERSONA_MATRIX_CI.md
  section: Regression triage workflow
last_generated_commit: ''
confidence: high
tags:
- docs
- PERSONA_MATRIX_CI
created_at: 1783195000.883054
updated_at: 1783195000.883054
---


When CI surfaces a regression:

1. **Identify the regressed cell.** The diff output names exactly
   `(persona, backend, model)`.
2. **Run the cell in isolation** locally to reproduce:
   ```bash
   python3 tests/portal5_persona_matrix.py \
       --workspace <ws> \
       --persona <slug-substring> \
       --model <model-substring> \
       --output /tmp/repro.json
   ```
3. **Inspect the failing scenarios.** The JSON shows per-scenario
   `results` with the assertion `name`, `passed`, `severity`, and
   `detail`. Find which assertion(s) flipped from PASS to FAIL.
4. **Triage cause.** Three common patterns:
   - **Model digest drift.** `ollama pull` was re-run and the model
     behaves differently. Acceptable cause; re-baseline if the new
     behavior is in spec.
   - **Persona prompt edit.** Recent persona change inadvertently
     constrained the model in a way the assertion library catches.
     Either revise the prompt or relax the assertion.
   - **Genuine regression.** The model is now worse. Demote per the
     fallback policy in `docs/<WORKSPACE>_FALLBACK_POLICY.md`.
