---
id: unit-known-limitations-spine-code-coverage-ratchet
kind: what
title: Spine Code-Surface Coverage Is Partial (Ratchet, Not a Cliff)
sources:
- type: code
  path: portal/platform/wiki/coverage.py
- type: code
  path: scripts/validate_system.py
last_generated_commit: baca992c674a3cbb36a619e8f62e7e88b8fccfff
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
- **Status**: RESOLVED — TASK_WIKI_ZERO_DEBT_V1 drove the uncovered set to empty and deleted the baseline; BR is now an absolute 100% gate with nothing to tolerate.
- **Description**: `validate_system.py` check **BR** (spine code coverage), backed by `portal/platform/wiki/coverage.py`, measures the fraction of eligible Python code surfaces cited by at least one non-aggregate, gate-passing wiki unit. At the time the gate landed (v8.0.0), coverage was about 7.6% (46 of 605 eligible files, per `coverage.py`'s module docstring). Aggregate `unit-code-*` units (auto-seeded by `seed_code.py`, which cites only the first five files of a subsystem while titling itself with the full count) are deliberately excluded from the numerator — counting them would grade the generator against its own output.
- **Mechanism**: The gate started as a ratchet — a pinned uncovered-set baseline file and CI failed only when that set *grew*. TASK_WIKI_ZERO_DEBT_V1 paid the debt down to zero: covering units were authored for every remaining surface, and once 100% was reached the baseline file was deleted. BR is now absolute: any uncovered eligible Python surface is an unconditional FAIL, with no baseline to absorb it.
- **Current state**: 100% of eligible code surfaces are cited by a gate-passing non-aggregate unit (`compute_coverage().uncovered == []`). There is no baseline file left to re-pin.
- **Next action**: Keep the discipline. New code must carry a covering unit at landing; BR fails outright until it does.

## Why

The ratchet exists to fix an authority inversion: docs generated from units were certified current by comparing them with the very units they came from, so nothing proved new code arrived documented. Measuring code citations from non-aggregate units only, and failing when the uncovered set grows, forces the forward direction — every new surface must earn its coverage. Re-pinning to 100% does not retire the gate; it changes its job from paying down debt to holding the line.
