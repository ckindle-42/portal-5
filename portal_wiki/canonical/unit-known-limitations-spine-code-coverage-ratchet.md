---
id: unit-known-limitations-spine-code-coverage-ratchet
kind: what
title: Spine Code-Surface Coverage Is Partial (Ratchet, Not a Cliff)
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  section: Spine Code-Surface Coverage Is Partial (Ratchet, Not a Cliff)
- type: code
  path: portal/platform/wiki/coverage.py
last_generated_commit: ''
confidence: high
tags:
- known-limitations
- coverage
- release
created_at: 1785381155.353122
updated_at: 1785459600
---

- **ID**: P5-SPINE-COVERAGE-001
- **Status**: OPEN — an active problem to pay down, not an accepted steady state. The ratchet
  is a floor that stops it from growing, not a reason to stop working on it.
- **Description**: `validate_system.py` check **BR** (spine code coverage ratchet) measures the
  fraction of eligible Python code surfaces cited by at least one non-aggregate wiki unit.
  At the time this gate landed (v8.0.0), coverage was **7.7%** (47 of 607 eligible files).
  Aggregate `unit-code-*` units (auto-seeded by `seed_code.py`, which cites only the first
  five files of a subsystem while titling itself with the full count) are deliberately
  excluded from the numerator — counting them would grade the generator against its own
  output, the same circularity the doc-generation arc paid for elsewhere.
- **Impact**: The vast majority of the codebase has no unit describing it. The spine's
  single-write-point discipline guarantees the *forward* direction (a unit change
  regenerates its docs); it does not by itself guarantee that new code arrives documented.
- **Mitigation shipped**: The gate is a ratchet, not a cliff. `config/spine_coverage_baseline.yaml`
  pins the current uncovered set; CI (check BR) fails only when that set *grows* — new code
  cannot land with zero coverage unnoticed. This prevents the debt from getting worse; it does
  not pay it down.
- **Current measurement (2026-07-30)**: **10.2%** (62 of 609 eligible files), with 547
  uncovered. The host-native MCP lifecycle, corpus-visibility, benign-corpus, and emergent
  alias audit units added coverage for their implementation, tests, launcher paths, and
  validator; the baseline was re-pinned downward to bank the gains.
- **Next action**: Backfill coverage for the 547 currently-uncovered surfaces (write covering
  units, re-pin the baseline down as each batch lands). Not completed in v8.0.0's release
  window — tracked as ongoing work, not closed out or deprioritized indefinitely.
