---
id: unit-known-limitations-spine-code-coverage-ratchet
kind: what
title: Spine Code-Surface Coverage Is Partial (Ratchet, Not a Cliff)
sources:
- type: code
  path: portal/platform/wiki/coverage.py
- type: code
  path: config/spine_coverage_baseline.yaml
- type: code
  path: scripts/validate_system.py
last_generated_commit: 0a5fcb6eea38bf284a96ceea702849491ba4d1c7
claims: []
confidence: high
tags:
- coverage
- known-limitations
- release
- verified-v1
created_at: 1785381155.353122
updated_at: 1785500996
---

- **ID**: P5-SPINE-COVERAGE-001
- **Status**: OPEN — an active problem to pay down, not an accepted steady state. The ratchet is a floor that stops the uncovered set from growing, not a reason to stop working on it.
- **Description**: `validate_system.py` check **BR** (spine code coverage ratchet), backed by `portal/platform/wiki/coverage.py`, measures the fraction of eligible Python code surfaces cited by at least one non-aggregate wiki unit. At the time the gate landed (v8.0.0), coverage was about 7.6% (46 of 605 eligible files, per `coverage.py`'s module docstring). Aggregate `unit-code-*` units (auto-seeded by `seed_code.py`, which cites only the first five files of a subsystem while titling itself with the full count) are deliberately excluded from the numerator — counting them would grade the generator against its own output.
- **Mechanism**: The gate is a ratchet, not a cliff. `config/spine_coverage_baseline.yaml` pins the current uncovered set; CI fails only when that set *grows* — new code cannot land with zero coverage unnoticed. This prevents the debt from getting worse; it does not itself pay it down.
- **Current state**: The baseline file now records 628 eligible surfaces with all 628 covered (`coverage_pct: 100.0`) — the uncovered list was driven to empty as covering units landed and the baseline was re-pinned downward after each audit batch. The ratchet still guards the set: any newly added Python surface that arrives without a covering unit makes the uncovered set grow and fails the gate.
- **Next action**: Keep the discipline. New code must carry a covering unit at landing, and the baseline must be re-pinned only downward (never hand-edited upward, which would defeat the authority inversion the gate exists to enforce).

## Why

The ratchet exists to fix an authority inversion: docs generated from units were certified current by comparing them with the very units they came from, so nothing proved new code arrived documented. Measuring code citations from non-aggregate units only, and failing when the uncovered set grows, forces the forward direction — every new surface must earn its coverage. Re-pinning to 100% does not retire the gate; it changes its job from paying down debt to holding the line.
