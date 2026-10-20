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

Every doc migration is an atomic green slice. After a single doc migrates the repo is fully working, the doc is generated and round-trip proven; the loop may stop after any commit and resume later with no cleanup. `render_report()` supplies the standing dashboard as `{migrated, unmigrated, gamed, blocks_total, coverage_pct, human_ratio}`. The dashboard reports migration state; generated-doc freshness is handled by an explicit docs build rather than a validate gate.

## Why

Mechanical termination exists so migration is never an open-ended rewrite campaign. Because each doc commits atomically and the candidate set is derived from git churn plus the Tier-1 tuple, an operator can interrupt the loop at any commit and resume later. The docs build is explicit, and live fact units are computed by the wiki MCP rather than synchronized into canonical files.
