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
check **BR** (spine coverage).

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
manifest-driven: `config/spine_surfaces.yaml` named each surface, the globs
that defined it, and the unit that documented it — but the manifest still bound
419 files one by one, so every new file forced an entry and the manifest churned
on routine commits.

DESIGN_ROOTS_REFINEMENT_20261020 B3 replaced the file bindings with directory
ownership: a module dir (`portal/modules/<name>`) is owned by
`unit-module-<name>`, a platform package by the gate-passing unit citing most
of its eligible files. Coverage asks whether every module, MCP and platform
package has a unit — a code edit inside a module demands no unit edit and no
manifest entry; a contract change (new module, new MCP, new platform package)
forces the unit that documents it. The manifest holds one entry per owned
directory and stops changing on routine commits.

`unit-code-<subsystem>` aggregate units (auto-seeded by `adapters/seed_code.py`)
remain excluded from coverage — counting a generator's own output would be the
circularity the doc-generation arc already paid for.
