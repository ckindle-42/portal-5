---
id: unit-DESIGN_WIKI-discovery-termination
kind: why
title: Discovery-driven loop with mechanical termination
sources:
- type: code
  path: portal/platform/wiki/migration.py
- type: code
  path: portal/platform/wiki/render.py
- type: code
  path: scripts/doc_ledger.py
last_generated_commit: 0a5fcb6eea38bf284a96ceea702849491ba4d1c7
claims: []
confidence: high
tags:
- design
- discovery
- loop
- verified-v1
- wiki
created_at: 1784941411.445575
updated_at: 1784941411.445575
---

The migration loop repeatedly calls `discover_unmigrated_docs()` and halts when the returned list is empty. The candidate set is computed at runtime as the union of the `TIER1_DOCS` tuple and the paths still present in `docs/.doc_ledger.yaml` (via `_ledger_doc_paths`); it is never chosen by hand on each run. Results are processed highest-priority first: `priority` is a git-churn count over the last 30 commits touching the file, plus a fixed boost for high-value seed docs, sorted descending.

Every doc migration is an atomic green slice. After a single doc migrates the repo is fully working, the doc is generated and round-trip proven, and its ledger entry can be pruned; the loop may stop after any commit and resume later with no cleanup. `render_report()` supplies the standing dashboard as `{migrated, unmigrated, gamed, blocks_total, coverage_pct, human_ratio}`. A graduated doc is retired from the ledger by `doc_ledger.py prune` (`prune_migrated`), so when discovery returns empty the ledger is empty too, and content-hash currency (validate check AW) governs from then on.

## Why

Mechanical termination exists so migration is never an open-ended rewrite campaign. Because each doc commits atomically and the candidate set is derived from git churn plus the ledger, an operator can interrupt the loop at any commit, resume later, and still find every intermediate state passes the migration gate. The ledger retirement matters as much as the loop: once AW diffs generated blocks against unit bodies directly, the commit-stamp model is redundant, and a shrinking ledger is simply the discovery surface collapsing to the Tier-1 set.
