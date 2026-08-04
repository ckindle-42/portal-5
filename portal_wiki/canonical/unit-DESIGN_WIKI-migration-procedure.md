---
id: unit-DESIGN_WIKI-migration-procedure
kind: what
title: 'Migration procedure: the per-doc loop body'
sources:
- type: code
  path: portal/platform/wiki/migration.py
- type: code
  path: portal/platform/wiki/render.py
- type: code
  path: scripts/doc_ledger.py
- type: code
  path: portal/platform/inference/sync_config.py
last_generated_commit: 0a5fcb6eea38bf284a96ceea702849491ba4d1c7
claims: []
confidence: high
tags:
- design
- procedure
- verified-v1
- wiki
created_at: 1784946277.748951
updated_at: 1784946277.748951
---

For each doc `D` returned by `discover_unmigrated_docs()`, processed highest priority first, the loop body is:

1. Read `D` and read HEAD reality; verify every substantive claim against actual code, config, or data and author units from HEAD truth, never from stale prose.
2. Decompose `D` into section-level units, reserving fact-atom decomposition for values that are reused or independently volatile (see the section-granularity unit).
3. Convert `D` into a shell whose substance is `WIKI:GENERATED` blocks plus `WIKI:HUMAN-OWNED` fences for the irreducible judgment.
4. Render through `sync-config`, which invokes `render_all_generated_blocks`, then prove round-trip: an edit to the unit propagates and a hand-edit inside a generated fence is clobbered.
5. Retire `D` from `docs/.doc_ledger.yaml` via `doc_ledger.py prune` (`prune_migrated`).
6. Verify the per-commit gate is green, commit, then re-discover and continue.

Each doc lands as one atomic commit, the repo is green after every commit, and the loop is resumable at any point without cleanup.

## Why

The procedure is a fixed loop body because a migration that cannot be verified at each step silently degrades into docs-are-the-source authoring. Rendering through `sync-config` and proving propagation and clobbering closes the loop before the ledger prune: a doc is only de-ledgered after its shell demonstrably tracks its units. The atomic-commit rule keeps every intermediate state buildable, which is what makes the loop safe to interrupt and resume.
