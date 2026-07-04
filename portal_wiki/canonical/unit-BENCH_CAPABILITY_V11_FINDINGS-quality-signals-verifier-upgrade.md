---
id: unit-BENCH_CAPABILITY_V11_FINDINGS-quality-signals-verifier-upgrade
kind: why
title: "BENCH_CAPABILITY_V11_FINDINGS \u2014 quality_signals verifier upgrade"
sources:
- type: design
  path: docs/BENCH_CAPABILITY_V11_FINDINGS.md
  section: quality_signals verifier upgrade
last_generated_commit: ''
confidence: high
tags:
- docs
- BENCH_CAPABILITY_V11_FINDINGS
created_at: 1783195000.827434
updated_at: 1783195000.827434
---


The coding and reasoning categories now have optional verifier callables:

| Category | Verifier method | Old approach |
|---|---|---|
| coding | Execute `merge_intervals` against unit tests | Keyword match on `def merge_intervals`, `list`, `tuple`, `intervals.sort`, `merged`, `overlap` |
| reasoning | Check numeric answer (bottleneck value ~2.29/hr, mention of beds) | Keyword match on `(bottleneck, capacity)`, `doctor`, `nurse`, `bed`, `(wait, arrival)`, `(minute, hour)` |

**Contrast test result:** A correct-but-differently-worded merge_intervals implementation now scores 1.0 (was 0.0 in keyword-only mode). A keyword-stuffed-but-wrong implementation now scores 0.0 (was 1.0 before). The fix is working.
