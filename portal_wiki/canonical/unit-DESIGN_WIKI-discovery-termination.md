---
id: unit-DESIGN_WIKI-discovery-termination
kind: why
title: Discovery-driven loop with mechanical termination
sources:
- type: design
  path: docs/DESIGN_WIKI_GENERATION_LOOP_V1.md
  commit: d869257b
  section: '4'
- type: code
  path: portal/platform/wiki/migration.py
  commit: d869257b
- type: code
  path: portal/platform/wiki/render.py
  commit: d869257b
last_generated_commit: d869257b
confidence: high
tags:
- design
- wiki
- discovery
- loop
created_at: 1784941411.445575
updated_at: 1784941411.445575
---

The migration loop processes whatever `discover_unmigrated_docs()` returns, highest-priority first, and **halts when it returns empty**. The doc list is computed, never hardcoded.

Each iteration is an **atomic green slice**: after any single doc migrates, the repo is fully working -- that doc is generated + round-trip-proven + de-ledgered; all other docs are untouched. The loop may stop after any commit and resume later with no cleanup.

Priority is a hint (most-important/most-churned first), not a fixed sequence. `render_report()` provides the standing progress dashboard: `{migrated, unmigrated, blocks_total, coverage_pct}`.

When `discover_unmigrated_docs` returns empty, the commit-stamp ledger (`docs/.doc_ledger.yaml`) should be at or near empty -- every graduated doc has been pruned by `doc_ledger.py prune`, and only content-hash currency (AW) governs them.
