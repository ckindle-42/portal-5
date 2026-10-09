---
id: D-T2-TRUTH-STRATIFICATION
question: Does finer index, sourcetype, and UTC-day stratification recover independently identifiable truth cells from the existing BOTS answer-key scenarios?
stage: window
why_not_binding: T1 excluded all three paired product slices, so no product stage was measured; this record evaluates scorer-plane truth coverage only.
arms: [coarse_entry_windows, index_sourcetype_day_cells]
metric: count of retained cells with every declared entity located in the named source and day, and every product event id reconciled to its source interval
adopt_if: retain the expanded stratification only if it yields at least one additional entity-complete cell, all cell intervals are UTC-day bounded and disjoint by event id, and the truth known-answer self-test and report validator pass
anti_goals:
  - do not add entities, sourcetypes, labels, or time ranges that are not supported by the published answer key and indexed telemetry
  - do not treat an answer-key entry as product-stage evidence or fit a threshold on these cells
  - do not use proxy windows or any target-facing operation
status: REJECTED
report: reports/review_eval/90890b3c9418457c/truth_stratification.json
result: "Zero of five completed independent parent-window replays exactly reconciled with T1 event IDs despite matching event counts; zero new cells were eligible, and the loop stopped under rule (b) because the measured product binding stage remains unmeasured and no family targets it."
---
The control is T1's whole-entry interval derivation. The candidate subdivides those same answer-key
scenarios by source and UTC day; it may increase usable truth units without changing the published
labels. T1 derived 7 of 27 whole entries and found 0 of 3 usable attack/benign index pairs.

Resolved: the current live source returned the T1 row counts for five unique parent windows, but
the product event ID sets changed. The repeated T1110 export was internally stable; only 804 of
22,397 IDs matched T1. The 616,196-event BOTSv2 T1190 window exceeded the 90-second export read
timeout. No new cell passed the preregistered parent-ID gate, so this data change is rejected as a
stratification improvement and no product arm ran.
