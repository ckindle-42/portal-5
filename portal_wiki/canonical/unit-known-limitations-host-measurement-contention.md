---
id: unit-known-limitations-host-measurement-contention
kind: what
title: Parallel Pre-Commit Workers Starved Live UAT
sources:
- type: code
  path: scripts/pytest_unit_with_tree_marker.py
- type: code
  path: .pre-commit-config.yaml
- type: code
  path: .github/workflows/unit-tests.yml
claims: []
confidence: high
tags:
- known-limitations
- testing
- memory
created_at: 1792627200
updated_at: 1792627200
---

#### Parallel pre-commit unit workers starved live UAT (2026-10-22)

- **ID**: P5-HOST-MEASURE-001
- **Status**: MITIGATED 2026-10-22 for the hook (`2fd0da3a`). Live measurements still require a quiet host.
- **Description**: The pre-commit unit hook used `pytest -n auto`. On this host that started 14 workers. Lane worktrees committing at the same time each ran that hook on the machine that serves the live stack. Host memory fell until UAT shots received HTTP 503 from the memory gate.
- **Mitigation**: `scripts/pytest_unit_with_tree_marker.py` caps the hook at `-n 4`. GitHub Actions keeps `-n auto` in `.github/workflows/unit-tests.yml` because that runner does not serve the live stack. A UAT, a WFE campaign, or any other live measurement on this host still needs the machine quiet, with no parallel unit-suite commits beside it.

#### Why

The unit suite is offline and mocked, so it looks safe to run beside a live eval. On this machine the workers still occupy the unified memory the load guard and oMLX's ceiling are measuring. A 503 during UAT then records host contention, which is a property of the night, not of the seat under test. Capping one hook bounds a single commit. Several commits plus a campaign still share the same pool, which is why a live number is only meaningful on a quiet host.
