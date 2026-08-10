---
id: unit-wiki-spine-coverage-gate
kind: mixed
title: Spine code-coverage gate (portal/platform/wiki/coverage.py)
sources:
- type: code
  path: portal/platform/wiki/coverage.py
- type: code
  path: config/spine_surfaces.yaml
- type: code
  path: portal/platform/wiki/adapters/seed_code.py
last_generated_commit: 916b1931ff69939a98aca98aa5ea64444ceee56c
claims: []
confidence: high
tags:
- BR
- coverage
- validate-system
- verified-v1
- wiki
created_at: 1785380311.8876002
updated_at: 1785380311.8876002
---

## What

`portal/platform/wiki/coverage.py` implements the code→spine authority
inversion: the guarantee that new code arrives documented, not just that
documentation tracks code. It is the data source for `validate_system.py`'s
check **BR** (spine code coverage ratchet).

## Why

The spine's single-write-point discipline already guarantees the forward
direction — a unit change regenerates its downstream docs. It never guaranteed
the converse: that new code arrives with a unit describing it. This module
measures the converse.

The gate went through two eras. It started as a ratchet pinning the uncovered
set (46/605 eligible files when it landed, 7.6%), then
TASK_WIKI_ZERO_DEBT_V1 drove the uncovered set to zero and made it absolute:
every eligible surface cited by a gate-passing non-aggregate unit, no baseline.

TASK_PORTAL_SIMPLIFY_V1 Phase R3 ended the per-file era. The absolute gate
rewarded a hand-authored unit per file, so knowledge accumulated at file
granularity and documentation mass grew in lockstep with code mass. The regrain
collapsed ~570 per-file mirrors into ~30 subsystem surfaces and coverage became
manifest-driven: `config/spine_surfaces.yaml` names each surface, the globs
that define it, and the unit that documents it. The gate asserts two parts —
every declared surface has a gate-passing unit citing paths matching its globs,
and every eligible `.py` file falls under some declared surface. New code inside
a documented surface costs nothing; new code outside one forces a deliberate
manifest entry. Code can still never arrive silently undocumented; it just no
longer costs a hand-authored unit per file. The wiki engine stays per-file as
the extraction-guarantee boundary (check AJ), verified by the R3 adversarial
probe: a new file under `portal/platform/wiki/` fails BR until registered.

`unit-code-<subsystem>` aggregate units (auto-seeded by `adapters/seed_code.py`)
remain excluded from coverage — counting a generator's own output would be the
circularity the doc-generation arc already paid for.
