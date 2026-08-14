---
id: unit-DESIGN_WIKI-discovery-termination
kind: why
title: Discovery-driven loop with mechanical termination
sources:
- type: code
  path: portal/platform/wiki/migration.py
- type: code
  path: portal/platform/wiki/render.py
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

The migration loop repeatedly calls `discover_unmigrated_docs()` and halts when the returned list is empty. The candidate set is computed at runtime as the `TIER1_DOCS` tuple unioned with any paths still present in a legacy ledger file (via `_ledger_doc_paths`); it is never chosen by hand on each run. Results are processed highest-priority first: `priority` is a git-churn count over the last 30 commits touching the file, plus a fixed boost for high-value seed docs, sorted descending.

Every doc migration is an atomic green slice. After a single doc migrates the repo is fully working, the doc is generated and round-trip proven; the loop may stop after any commit and resume later with no cleanup. `render_report()` supplies the standing dashboard as `{migrated, unmigrated, gamed, blocks_total, coverage_pct, human_ratio}`. Content-hash currency (validate check AW) diffs every generated block against its unit body, so the candidate discovery set collapses to the Tier-1 set once the legacy commit-stamp ledger is gone.

## Why

Mechanical termination exists so migration is never an open-ended rewrite campaign. Because each doc commits atomically and the candidate set is derived from git churn plus the Tier-1 tuple, an operator can interrupt the loop at any commit, resume later, and still find every intermediate state passes the migration gate. The legacy commit-stamp ledger (the `docs`-tree ledger file and its `scripts`-tree pruning script) was deleted in TASK_WIKI_ZERO_DEBT_V1 once its empty state made the `AK` doc-currency check a no-op; AW diffs generated blocks against unit bodies directly, so the commit-stamp model is redundant and the discovery surface is just the Tier-1 set.
