---
id: unit-compliance-prove-then-scale
kind: mixed
title: "PROVE_THEN_SCALE_V1 — the population as text, the mapping sweep, the review surfaces"
sources:
- type: code
  path: portal/modules/compliance/core/reading_material.py
- type: code
  path: portal/modules/compliance/core/sweep.py
- type: code
  path: portal/modules/compliance/core/contradictions.py
---

The PROVE_THEN_SCALE_V1 campaign's product code (report:
`reports/compliance/PROVE_THEN_SCALE_V1.md`).

`reading_material.py` renders a requirement's scope as the material a reading
reads: the standard's fixed body FIRST (byte-identical per revision, sha
recorded — the shared prompt-cache prefix and the cluster shard key), then the
requirement's own anchors, operator edges and notes, every entry labelled with
its side and standing. Operator sections arrive with their document
neighbourhood — parent heading, siblings in reading order, same-document
sections the graph ties to this requirement — capped at
`NEIGHBOURHOOD_MAX_SECTIONS`/`NEIGHBOURHOOD_MAX_CHARS`, the cap stated in the
rendered label.

`sweep.py` is the standard-ordered sweep: `STANDARD_ORDER` records the
dependency order and each placement's reason; `map_read` is the map unit —
one requirement, a deterministic population, one call, a receipt whose closure
carries the determination outcomes; `parse_determinations` reads the answer's
JSON block; `sweep_standard` runs one revision and measures the cache on
`prompt_eval_duration` (never `prompt_eval_count`); `reduce_standard` is the
reduce half — one call over the sweep's ANSWERS, never the populations;
`refs_for_standard` selects exactly one revision's nodes (family matching
double-read sibling revisions — measured, fixed); `sweep_answers` reloads a
standard's retained answers from the receipts.

`contradictions.py` is the operator's review-by-exception:
`scan_contradictions` surfaces cross-reading disagreement (relation conflicts,
determinations against human-rejected edges, disagreements with approved
edges); `drill_down` opens one answer — or one retained run by `run_id` — to
the verbatim text of every cited section on both sides.

Contract tests: `tests/unit/test_compliance_prove_then_scale.py`.
Measured live: `reports/compliance/prove_then_scale/`.

## Why

A reading can only be as good as the material it is handed and the
edges it is allowed to write. These three modules are the campaign's
answer: the population rendered complete and labelled (nothing for the
model to search for), the sweep that turns readings into typed,
provenance-carrying mapping edges under a checker that refuses what it
cannot trace, and the review surfaces that keep the human's queue down
to real questions.
