---
id: unit-scripts-spine_census
kind: mixed
title: "Script \u2014 spine_census"
sources:
- type: code
  path: scripts/spine_census.py
last_generated_commit: 481c0daaa9f701c6dfc81e76f2040755f7cd8334
claims: []
confidence: high
tags:
- scripts
- verified-v1
created_at: 1785880000.0
updated_at: 1785880000.0
---

Spine census separates the wiki's knowledge store into granularity populations instead of reporting total size. A mirror unit cites exactly one code path, which means its scope was probably set by the coverage gate's filesystem walk rather than by a decision; a surface unit cites several paths or pairs code with config, which reflects a subsystem or contract boundary. The tool also counts orphaned units whose cited paths no longer resolve and units carrying bound claims — the only population the drift census can mechanically verify.

## Why

The documentation apparatus grew to the same mass as the code because the gate rewarded file-scoped units, and file granularity is not knowledge granularity. Decisions, contracts, and constraints live at subsystem altitude. This tool makes the regrain arguable from data: it quantifies how many units are mirrors, how many words they hold, and which directories cluster enough mirrors to consolidate into a single surface. The `--surfaces` mode emits that clustering as a proposed manifest for operator approval.

## Interfaces

Operator or agent tool run from the repo root. Default output is a formatted report; `--json` emits totals, `--surfaces` emits the proposed consolidation manifest, `--top N` limits the report's per-section rows. Exit code is 0 on success, 1 if no canonical units are found.

## Gotchas

Eligibility mirrors the coverage gate's own walk over git-tracked files, so counts stay comparable with the gate it is arguing against. Report output is advisory by design — it proposes, it never archives.
