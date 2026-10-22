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
- type: code
  path: scripts/host_quiet.py
- type: code
  path: scripts/uat_security.py
- type: code
  path: scripts/uat_engines.py
- type: code
  path: scripts/orchestration_acceptance.py
- type: code
  path: scripts/seat_preflight.py
claims: []
confidence: high
tags:
- known-limitations
- testing
- memory
created_at: 1792627200
updated_at: 1792668000
---

#### Parallel pre-commit unit workers starved live UAT (2026-10-22)

- **ID**: P5-HOST-MEASURE-001
- **Status**: MITIGATED 2026-10-22 for the hook (`2fd0da3a`) and for the UAT, acceptance, and seat-preflight entry points (`2182ae1e`). A live measurement still requires a quiet host; those runners now refuse to start when it is not.
- **Description**: The pre-commit unit hook used `pytest -n auto`. On this host that started 14 workers. Lane worktrees committing at the same time each ran that hook on the machine that serves the live stack. Host memory fell until UAT shots received HTTP 503 from the memory gate.
- **Mitigation**: `scripts/pytest_unit_with_tree_marker.py` caps the hook at `-n 4`. GitHub Actions keeps `-n auto` in `.github/workflows/unit-tests.yml` because that runner does not serve the live stack. `scripts/host_quiet.py` is the start gate for `scripts/uat_security.py`, `scripts/uat_engines.py`, `scripts/orchestration_acceptance.py`, and `scripts/seat_preflight.py`. `begin_run` samples pipeline load-plan headroom (else `vm_stat` free plus inactive), pipeline busy requests, and other heavy processes (a dispatch lane job, pytest/xdist, or a WFE/bench run). It blocks when the process scan fails, one of those processes is running, the pipeline reports an active request, or headroom is missing or below `UAT_MIN_HOST_HEADROOM_GIB` (default 1.5 GiB, the same floor the memory gate uses). `--force` records the overridden blockers and continues. `finish_run` attaches an end snapshot. The hook cap bounds one commit. This preflight is what stops a live shot from starting on a busy host. A WFE campaign that does not go through those entry points still needs the machine quiet on its own.

#### Why

The unit suite is offline and mocked, so it looks safe to run beside a live eval. On this machine the workers still occupy the unified memory the load guard and oMLX's ceiling are measuring. A 503 during UAT then records host contention, which is a property of the night, not of the seat under test. Capping one hook bounds a single commit. The host-quiet preflight refuses the guarded runners when that contention is already visible. Several commits plus a campaign that does not use those runners still share the same pool, which is why a live number is only meaningful on a quiet host.
