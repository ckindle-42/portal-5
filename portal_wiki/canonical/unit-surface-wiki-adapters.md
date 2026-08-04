---
id: unit-surface-wiki-adapters
kind: mixed
title: "Wiki adapters \u2014 Portal wiring: seeds, writeback, source connectors"
sources:
- type: code
  path: portal/platform/wiki/adapters/*.py
last_generated_commit: 22007054d6cba73357ea3c5d7d7c97f5c252d7dc
claims: []
confidence: high
tags:
- authored-v1
- platform
- wiki
created_at: 1785885800.0
updated_at: 1785885800.0
---

The `portal/platform/wiki/adapters/*.py` wiring binds the stack-agnostic wiki
engine to the portal-5 repository. One side reaches outward: `GitSourceConnector`
walks the repo for Python modules and design docs, and `PortalInference` answers
seeder generation calls against Ollama's `/api/generate`. The other side projects
and writes back: `derive_body` renders the AST surface, the seeders derive units
from the repo, and every loop result enters through one confirm-gated
`propose_unit` path.

## Why

The engine's interfaces are Portal-agnostic so it can be tested without a real
repo; each Portal-specific fact therefore lives in an adapter. Two disciplines
follow. Seeders are machine-derived projections, so the coverage gate excludes
them from its numerator — counting them would grade the generator against its own
output. Write-backs are claims about the platform, so a bench verdict, gap
resolution, validated investigation finding, or module toggle waits on the same
confirm gate.

## Interfaces

`GitSourceConnector.iter_sources()` feeds the code seeder and the fact
derivation. `derive_body` produces the projection `check_substance` compares a
unit against, returning empty text when the file cannot be parsed so the
comparison is skipped, never raised. `seed_code`, `seed_intent`,
`seed_technique_signatures`, and `seed_dcsync_specifically` derive WHAT and WHY
units. `writeback_bench_result`, `writeback_gap_resolution`,
`writeback_investigation_findings`, and `module_state_change` funnel through
`propose_unit`, whose `auto_confirm` flag bypasses the gate for a trusted
harness.

## Gotchas

`discover_python_files` is the shared eligibility definition the coverage gate
mirrors, so both sides agree on what counts. Technique-signature ids follow the
machine-seeded pattern the calibration excludes — derived, not authored.
`module_state_change` flips the `enabled:` field in place, and `enabled_modules()`
trusts the resulting body, so the write must be complete, not partial.
