---
id: unit-surface-wiki
kind: mixed
title: "Wiki engine \u2014 schema, store, provenance, maintenance loop"
sources:
- type: code
  path: portal/platform/wiki/*.py
last_generated_commit: 22007054d6cba73357ea3c5d7d7c97f5c252d7dc
claims: []
confidence: high
tags:
- authored-v1
- platform
- wiki
created_at: 1785885600.0
updated_at: 1785885600.0
---

The wiki engine is the canonical layer's runtime: every unit is one markdown
file under a git-backed store, the maintenance loop keeps machine-derived
units current while authored ones persist, the provenance ledger records the
commit each derived unit was generated against, and the interfaces module
draws the stack-agnostic boundary that keeps the engine portable.

## Why

Units are markdown files so they are diffable and need no database service;
the frontmatter round-trip must be an exact inverse or a re-save destroys
data. Persistence is git-backed and directory-overridable so tests redirect
writes into a tmp_path. The maintenance loop re-derives only WHAT units,
because advancing HEAD alone never makes an authored unit stale — authored
units are the spine, provenance is navigation, not reverse authority. The
propose/confirm split keeps arbitrary proposals out of canonical until
confirmation promotes them with citations intact, and the engine depends on
interfaces, never on Portal runtime code.

## Interfaces

The store exposes `save_unit`, `load_unit`, `load_all`, `load_archived`, and
`delete_unit`, with `set_canonical_dir` for redirection. `check_staleness`
and `update_what_units` drive the maintenance loop, `canonical_snapshot_hash`
is its churn detector, and `wiki_status` reports health. `propose_unit` and
`confirm_unit` stage and promote proposals under `WritebackCollisionError`,
while `append_entry` records the ledger. `InferenceBackend` and
`SourceConnector` are the adapter contracts; `to_markdown`, `from_markdown`,
and `content_hash` are the schema round-trip.

## Gotchas

`save_unit` overwrites by unit id, so re-seeding is idempotent but a field
missing from `to_frontmatter` is silently destroyed on re-save; the store's
directory overrides are process-global side effects that tests must reset,
and `load_all` skips malformed files rather than crashing.
