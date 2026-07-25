---
id: unit-DESIGN_WIKI-migration-procedure
kind: what
title: 'Migration procedure: the per-doc loop body'
sources:
- type: design
  path: docs/DESIGN_WIKI_GENERATION_LOOP_V1.md
  commit: 05e42ec2
  section: Migration procedure
- type: code
  path: portal/platform/wiki/migration.py
  commit: 05e42ec2
last_generated_commit: 05e42ec2
confidence: high
tags:
- design
- wiki
- procedure
created_at: 1784946277.748951
updated_at: 1784946277.748951
---

For each doc `D` returned by `discover_unmigrated_docs()` (highest priority first):

1. Read `D` and read HEAD reality. For every substantive claim, verify against actual code/config/data. Author units from HEAD truth, not stale prose.
2. Decompose `D` into section-level units (A2 granularity rule).
3. Convert `D` to a shell of WIKI:GENERATED blocks and WIKI:HUMAN-OWNED fences for irreducible judgment.
4. Render via `sync-config`, prove round-trip (edit-propagates, hand-edit-is-clobbered).
5. Retire `D` from commit-stamp ledger via `doc_ledger.py prune`.
6. Verify green, commit. Re-discover and continue.

Each doc is one atomic commit. The repo is green after every commit. The loop is resumable at any point.
